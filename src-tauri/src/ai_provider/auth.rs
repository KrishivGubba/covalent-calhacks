/// Auth module: fetches the current user's Auth0 JWT from the local Python server.
///
/// The Python server (Flask or FastAPI) manages user sessions in an encrypted SQLite 
/// database (SQLCipher + macOS Keychain). Rather than replicating that logic in Rust, 
/// we call the `/auth/current` endpoint which returns the active access_token for the 
/// logged-in desktop user.
use serde::Deserialize;

const DEFAULT_BACKEND_URL: &str = "http://localhost:5001";
const FETCH_TIMEOUT_SECS: u64 = 5;

/// Full session info returned by `/auth/current`.
#[derive(Debug, Deserialize, Clone)]
pub struct CurrentSession {
    pub authenticated: bool,
    pub access_token: Option<String>,
    pub user_id: Option<String>,
    pub user_info: Option<serde_json::Value>,
    #[serde(default)]
    pub expired: bool,
}

/// Fetch the active user session from the Python backend.
///
/// Returns `None` if the server is unreachable, no user is logged in, or the token
/// is expired. Callers should treat `None` as "unauthenticated" and fall back
/// to direct API-key-based providers.
pub async fn fetch_current_session(backend_url: &str) -> Option<CurrentSession> {
    let url = format!("{}/auth/current", backend_url.trim_end_matches('/'));

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(FETCH_TIMEOUT_SECS))
        .build()
        .ok()?;

    let response = client.get(&url).send().await.ok()?;

    if !response.status().is_success() {
        return None;
    }

    let session: CurrentSession = response.json().await.ok()?;

    if session.authenticated && !session.expired {
        Some(session)
    } else {
        None
    }
}

/// Convenience helper: return just the access_token string, or `None`.
pub async fn fetch_current_jwt(backend_url: &str) -> Option<String> {
    fetch_current_session(backend_url)
        .await
        .and_then(|s| s.access_token)
}

/// Return the active session using the default backend URL (`http://localhost:5001`),
/// falling back to the `FLASK_BASE_URL` environment variable for backward compatibility.
pub async fn fetch_current_session_default() -> Option<CurrentSession> {
    let url = std::env::var("FLASK_BASE_URL")
        .unwrap_or_else(|_| DEFAULT_BACKEND_URL.to_string());
    fetch_current_session(&url).await
}

/// Return just the JWT using the default backend URL.
pub async fn fetch_current_jwt_default() -> Option<String> {
    fetch_current_session_default()
        .await
        .and_then(|s| s.access_token)
}
