import { createAsyncThunk, createSelector, createSlice } from "@reduxjs/toolkit";
import { getLinesConfig } from "../api/client";
import { logout, changeLine, clearLine } from "./authSlice";

export const fetchLines = createAsyncThunk("lines/fetch", async () => {
  return await getLinesConfig();
});

const initialState = {
  lines: [],
  status: "idle", // idle | loading | succeeded | failed
  error: null,
};

const linesSlice = createSlice({
  name: "lines",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      // Logging out drops the previous line's config, so the next login
      // (possibly a different line) fetches its own.
      .addCase(logout, () => initialState)
      .addCase(changeLine, () => initialState)
      .addCase(clearLine, () => initialState)
      .addCase(fetchLines.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchLines.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.lines = action.payload;
      })
      .addCase(fetchLines.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message;
      });
  },
});

export default linesSlice.reducer;

// ---- Selectors ----
export const selectLinesStatus = (state) => state.lines.status;

export const selectLineByKey = (state, key) =>
  state.lines.lines.find((l) => l.line_key === key) || null;

const NO_IDS = [];

/** Flattened, enabled-only, sorted slave_id list for a line's gauges across all its hosts.
 * Memoized: it must return the *same* array until the line changes, otherwise every
 * store update would re-render everything that uses it. */
export const selectGaugeIdsForLine = createSelector([selectLineByKey], (line) => {
  if (!line) return NO_IDS;
  const ids = line.hosts.flatMap((h) =>
    h.gauges.filter((g) => g.enabled).map((g) => g.slave_id)
  );
  return ids.sort((a, b) => a - b);
});
