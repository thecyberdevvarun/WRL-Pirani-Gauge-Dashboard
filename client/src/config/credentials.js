// These credentials are intentionally hardcoded in the frontend and are
// NOT checked against the backend database — the login screen displays
// them as clickable cards so an operator just taps theirs, picks a line,
// and logs in. Change the password values here if they need to rotate.
export const CREDENTIALS = [
  { username: "operator", password: "operator@123", role: "Operator" },
];

export function findCredential(username, password) {
  return (
    CREDENTIALS.find((c) => c.username === username && c.password === password) || null
  );
}
