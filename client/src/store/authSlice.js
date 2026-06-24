import { createSlice } from "@reduxjs/toolkit";

const STORAGE_KEY = "pirani.session";

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.username || !parsed?.line) return null;
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
  line: saved?.line || null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    login(state, action) {
      const { username, role, line } = action.payload;
      state.isAuthenticated = true;
      state.username = username;
      state.role = role;
      state.line = line;
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ username, role, line }));
    },
    logout(state) {
      state.isAuthenticated = false;
      state.username = null;
      state.role = null;
      state.line = null;
      localStorage.removeItem(STORAGE_KEY);
    },
    changeLine(state, action) {
      state.line = action.payload;
      if (state.isAuthenticated) {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ username: state.username, role: state.role, line: action.payload })
        );
      }
    },
  },
});

export const { login, logout, changeLine } = authSlice.actions;
export default authSlice.reducer;
