import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import linesReducer from "./linesSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    lines: linesReducer,
  },
});
