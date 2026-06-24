import { useCallback, useEffect, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import TodayStatsBar from "../components/TodayStatsBar";
import StatusCountersBar from "../components/StatusCountersBar";
import StatusLegend from "../components/StatusLegend";
import ConveyorTrack from "../components/ConveyorTrack";
import ScanPanel from "../components/ScanPanel";
import DetailPanel from "../components/DetailPanel";
import LastReportsTable from "../components/LastReportsTable";
import { getFixtures, getReports, openFixturesStream } from "../api/client";
import { toast } from "react-hot-toast";
import { getLineConfig } from "../config/lines";

export default function FixturesPage() {
  const line = useSelector((s) => s.auth.line);
  const lineConfig = getLineConfig(line);
  const gaugeCount = lineConfig?.gaugeCount ?? 0;

  const [fixtures, setFixtures] = useState([]);
  const [lastReports, setLastReports] = useState([]);
  const [gaugeId, setGaugeId] = useState("");
  const [selectedGaugeId, setSelectedGaugeId] = useState(null);

  const refreshFixtures = useCallback(() => {
    getFixtures()
      .then(setFixtures)
      .catch(() => toast.error("Could not refresh fixtures"));
  }, []);

  const refreshLastReports = useCallback(() => {
    getReports({ limit: 10, line: line || undefined })
      .then(setLastReports)
      .catch(() => {});
  }, [line]);

  // Prefer the realtime SSE stream; fall back to polling if it errors.
  useEffect(() => {
    refreshFixtures();
    let pollTimer = null;
    const es = openFixturesStream(
      (data) => setFixtures(data),
      () => {
        es.close();
        pollTimer = setInterval(refreshFixtures, 2000);
      }
    );
    return () => {
      es.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [refreshFixtures]);

  useEffect(() => {
    refreshLastReports();
    const t = setInterval(refreshLastReports, 8000);
    return () => clearInterval(t);
  }, [refreshLastReports]);

  // Only the gauges that belong to the currently selected line.
  const lineFixtures = useMemo(
    () => (gaugeCount ? fixtures.filter((f) => f.slave_id >= 1 && f.slave_id <= gaugeCount) : []),
    [fixtures, gaugeCount]
  );

  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, run: 0, idle: 0 };
    lineFixtures.forEach((f) => {
      if (f.status === "PASS") c.pass++;
      else if (f.status === "FAIL") c.fail++;
      else if (f.status === "RUNNING") c.run++;
      else c.idle++;
    });
    return c;
  }, [lineFixtures]);

  const selectedFixture = lineFixtures.find((f) => f.slave_id === selectedGaugeId) || null;

  const handleSelect = (id) => {
    setGaugeId(String(id));
    setSelectedGaugeId(id);
  };

  const handleRowClick = (gaugeIdFromRow) => handleSelect(gaugeIdFromRow);

  return (
    <>
      <TodayStatsBar />
      <StatusCountersBar counts={counts} />

      <div className="p-4 max-w-[1900px] mx-auto">
        <StatusLegend />

        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_420px] gap-5 items-start">
          <ScanPanel
            gaugeId={gaugeId}
            gaugeCount={gaugeCount}
            onGaugeIdChange={setGaugeId}
            onStarted={() => {
              refreshFixtures();
              refreshLastReports();
            }}
          />

          <ConveyorTrack
            fixtures={lineFixtures}
            gaugeCount={gaugeCount}
            lineLabel={lineConfig?.label}
            onSelect={handleSelect}
          />

          <DetailPanel
            gaugeId={selectedGaugeId}
            fixture={selectedFixture}
            onStopped={() => {
              refreshFixtures();
            }}
          />
        </div>
      </div>

      <LastReportsTable rows={lastReports} onRowClick={handleRowClick} />
    </>
  );
}
