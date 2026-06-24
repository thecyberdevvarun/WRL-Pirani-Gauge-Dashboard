// Canonical list of conveyor lines and how many physical Pirani gauge
// fixtures (slave_id 1..N) are wired up on each one. This drives:
//   - the line picker on the login screen
//   - how many gauge nodes the conveyor track renders
//   - the gauge-id range validation in the Start Test panel
export const LINES = [
  { key: "FREEZER", label: "Freezer", gaugeCount: 64 },
  { key: "CHOCOLATE", label: "Chocolate", gaugeCount: 22 },
  { key: "SUS", label: "SUS", gaugeCount: 15 },
];

export function getLineConfig(key) {
  return LINES.find((l) => l.key === key) || null;
}

export function getGaugeCount(key) {
  return getLineConfig(key)?.gaugeCount ?? 0;
}
