use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::time::Duration;

pub const APP: &str = "FormDAM";
pub const SHELL_ENV: &str = "FORMDAM_SHELL_PID";
pub const ADDRESS_WAIT: Duration = Duration::from_secs(90);
pub const EXIT_WAIT: Duration = Duration::from_secs(1);
pub const EXIT_STEP: Duration = Duration::from_millis(50);
pub const BUSY_CODE: i32 = 2;
const DATA_NAME: &str = "DAM";
const MAC_LOGS: &str = "formDAM";
const LOG_NAME: &str = "engine.log";
const TAIL_LINES: usize = 12;
const LINE_CHARS: usize = 300;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Wait {
    Address,
}

impl Wait {
    pub fn limit(self) -> Duration {
        match self {
            Wait::Address => ADDRESS_WAIT,
        }
    }

    pub fn what(self) -> &'static str {
        match self {
            Wait::Address => "its engine to say which address it serves on",
        }
    }
}

#[derive(Debug, PartialEq)]
pub enum Failure {
    Missing,
    NotStarted(String),
    Stopped(Option<i32>),
    TimedOut(Wait),
    Window,
}

#[derive(Default)]
pub struct Tail(VecDeque<String>);

impl Tail {
    pub fn push(&mut self, line: &str, secret: &str) {
        if !secret.is_empty() && line.contains(secret) {
            return;
        }
        let clean: String = line.chars().filter(|c| !c.is_control()).take(LINE_CHARS).collect();
        if clean.trim().is_empty() {
            return;
        }
        if self.0.len() == TAIL_LINES {
            self.0.pop_front();
        }
        self.0.push_back(clean);
    }

    pub fn lines(&self) -> Vec<String> {
        self.0.iter().cloned().collect()
    }
}

pub fn sentence(failure: &Failure) -> String {
    match failure {
        Failure::Missing => format!("{APP} could not start: its engine program is missing from the install. Installing {APP} again puts it back."),
        Failure::NotStarted(reason) => format!("{APP} could not start its engine: {reason}"),
        Failure::Stopped(Some(BUSY_CODE)) => format!("{APP} could not start: another copy of its engine holds its settings folder."),
        Failure::Stopped(Some(code)) => format!("{APP} could not start: its engine stopped with code {code} before the window could open."),
        Failure::Stopped(None) => format!("{APP} could not start: its engine stopped before the window could open."),
        Failure::TimedOut(wait) => format!("{APP} could not start: it waited {} seconds for {} and that did not happen.", wait.limit().as_secs(), wait.what()),
        Failure::Window => format!("{APP} could not open its window."),
    }
}

pub fn message(failure: &Failure, tail: &[String], log: Option<&Path>) -> String {
    let mut text = sentence(failure);
    if !tail.is_empty() {
        text.push_str("\n\nThe engine's last lines:\n");
        text.push_str(&tail.join("\n"));
    } else if matches!(failure, Failure::Stopped(_) | Failure::TimedOut(_)) {
        text.push_str("\n\nThe engine wrote nothing before that.");
    }
    if let Some(path) = log {
        text.push_str("\n\nThe engine's log: ");
        text.push_str(&path.to_string_lossy());
    }
    text
}

pub fn log_folder(os: &str, var: &dyn Fn(&str) -> Option<String>, home: Option<&Path>) -> Option<PathBuf> {
    match os {
        "macos" => Some(home?.join("Library").join("Logs").join(MAC_LOGS)),
        "windows" => match var("APPDATA") {
            Some(roaming) => Some(PathBuf::from(roaming).join(DATA_NAME)),
            None => Some(home?.join(DATA_NAME)),
        },
        _ => Some(home?.join(".local").join("share").join(DATA_NAME)),
    }
}

pub fn log_path(os: &str, var: &dyn Fn(&str) -> Option<String>, home: Option<&Path>) -> Option<PathBuf> {
    log_folder(os, var, home).map(|folder| folder.join(LOG_NAME))
}

pub fn engine_log() -> Option<PathBuf> {
    log_path(std::env::consts::OS, &|name| std::env::var(name).ok(), std::env::home_dir().as_deref())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn only(name: &'static str, value: &'static str) -> impl Fn(&str) -> Option<String> {
        move |asked| (asked == name).then(|| value.to_string())
    }

    #[test]
    fn the_tail_keeps_the_last_lines_and_never_a_line_with_the_key() {
        let mut tail = Tail::default();
        for n in 0..15 {
            tail.push(&format!("line {n}"), "k3y");
        }
        tail.push("GET /?dam-key=k3y 200", "k3y");
        tail.push("   ", "k3y");
        tail.push("\u{1b}[31mred\u{1b}[0m\r", "k3y");
        tail.push(&"x".repeat(1000), "");
        let lines = tail.lines();
        assert_eq!(lines.len(), TAIL_LINES);
        assert_eq!(lines[0], "line 5");
        assert_eq!(lines[TAIL_LINES - 2], "[31mred[0m");
        assert_eq!(lines[TAIL_LINES - 1].len(), LINE_CHARS);
        assert!(lines.iter().all(|line| !line.contains("k3y")));
    }

    #[test]
    fn every_failure_has_its_sentence_the_last_lines_and_the_log() {
        let log = Path::new("/home/u/.local/share/DAM/engine.log");
        let said = vec!["formDAM is already running on /home/u/.config/formDAM (engine process 7).".to_string()];
        let busy = message(&Failure::Stopped(Some(BUSY_CODE)), &said, Some(log));
        assert!(busy.starts_with("FormDAM could not start: another copy of its engine holds its settings folder."));
        assert!(busy.contains("The engine's last lines:\nformDAM is already running on /home/u/.config/formDAM (engine process 7)."));
        assert!(busy.ends_with("The engine's log: /home/u/.local/share/DAM/engine.log"));
        assert!(message(&Failure::Stopped(Some(3)), &[], Some(log)).contains("stopped with code 3"));
        assert!(message(&Failure::Stopped(None), &[], None).ends_with("The engine wrote nothing before that."));
        assert!(message(&Failure::Missing, &[], None).ends_with("puts it back."));
        assert!(sentence(&Failure::NotStarted("Access is denied.".to_string())).ends_with("its engine: Access is denied."));
        assert_eq!(sentence(&Failure::Window), "FormDAM could not open its window.");
    }

    #[test]
    fn a_wait_that_runs_out_says_how_long_and_for_what() {
        assert_eq!(Wait::Address.limit(), Duration::from_secs(90));
        assert!(sentence(&Failure::TimedOut(Wait::Address)).contains("waited 90 seconds for its engine to say which address it serves on"));
    }

    #[test]
    fn the_log_is_where_the_engine_writes_it() {
        let home = Path::new("/home/u");
        let none = |_: &str| None;
        assert_eq!(log_path("linux", &none, Some(home)), Some(home.join(".local").join("share").join("DAM").join("engine.log")));
        assert_eq!(log_path("linux", &only("XDG_DATA_HOME", "/x/share"), Some(home)), Some(home.join(".local").join("share").join("DAM").join("engine.log")));
        assert_eq!(log_path("macos", &none, Some(home)), Some(home.join("Library").join("Logs").join("formDAM").join("engine.log")));
        assert_eq!(log_path("windows", &only("APPDATA", "/roaming"), Some(home)), Some(Path::new("/roaming").join("DAM").join("engine.log")));
        assert_eq!(log_path("windows", &only("APPDATA", "/roaming"), None), Some(Path::new("/roaming").join("DAM").join("engine.log")));
        assert_eq!(log_path("windows", &none, Some(home)), Some(home.join("DAM").join("engine.log")));
        assert_eq!(log_path("linux", &none, None), None);
        assert_eq!(log_path("macos", &none, None), None);
    }
}
