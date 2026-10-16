import { createSlice } from "@reduxjs/toolkit";

const STORAGE_KEY = "pirani.session";

// The server session (signed cookie) is the real authority; this is only the
// browser's copy so a refresh does not flash the login page. If the server
// disagrees, the next API call returns 401/409 and App.jsx corrects it.
function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.username) return null;
    return parsed;
  } catch {
    return null;
  }
}

const saved = loadSession();

const initialState = {
  isAuthenticated: !!saved,
  username: saved?.username || null,
  role: saved?.role || null,
  line: saved?.line || null, // the line being worked on; null until chosen
  lines: saved?.lines || [], // every line this user may use: [{ key, label, gauge_count }]
};

function persist(state) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      username: state.username,
      role: state.role,
      line: state.line,
      lines: state.lines,
    })
  );
}

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    login(state, action) {
      const { username, role, line = null, lines = [] } = action.payload;
      state.isAuthenticated = true;
      state.username = username;
      state.role = role;
      state.line = line;
      state.lines = lines;
      persist(state);
    },
    logout(state) {
      state.isAuthenticated = false;
      state.username = null;
      state.role = null;
      state.line = null;
      state.lines = [];
      localStorage.removeItem(STORAGE_KEY);
    },
    changeLine(state, action) {
      state.line = action.payload;
      if (state.isAuthenticated) persist(state);
    },
    // The server says no line is selected (e.g. its session restarted):
    // send the user back to the line chooser.
    clearLine(state) {
      state.line = null;
      if (state.isAuthenticated) persist(state);
    },
  },
});

export const { login, logout, changeLine, clearLine } = authSlice.actions;
export default authSlice.reducer;
