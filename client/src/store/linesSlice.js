import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { getLinesConfig } from "../api/client";

export const fetchLines = createAsyncThunk("lines/fetch", async () => {
  return await getLinesConfig();
});

const linesSlice = createSlice({
  name: "lines",
  initialState: {
    lines: [],
    status: "idle", // idle | loading | succeeded | failed
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
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

export const selectLineOptions = (state) =>
  state.lines.lines.map((l) => ({
    key: l.line_key,
    label: l.line_label,
    gaugeCount: l.hosts.reduce(
      (n, h) => n + h.gauges.filter((g) => g.enabled).length,
      0
    ),
  }));

export const selectLineByKey = (state, key) =>
  state.lines.lines.find((l) => l.line_key === key) || null;

/** Flattened, enabled-only, sorted slave_id list for a line's gauges across all its hosts. */
export const selectGaugeIdsForLine = (state, key) => {
  const line = selectLineByKey(state, key);
  if (!line) return [];
  const ids = line.hosts.flatMap((h) =>
    h.gauges.filter((g) => g.enabled).map((g) => g.slave_id)
  );
  return ids.sort((a, b) => a - b);
};
