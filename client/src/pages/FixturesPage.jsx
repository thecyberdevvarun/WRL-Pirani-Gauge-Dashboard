import { useCallback, useEffect, useMemo, useState } from "react";
import TodayStatsBar from "../components/TodayStatsBar";
import StatusCountersBar from "../components/StatusCountersBar";
import StatusLegend from "../components/StatusLegend";
import ConveyorTrack from "../components/ConveyorTrack";
import ScanPanel from "../components/ScanPanel";
import DetailPanel from "../components/DetailPanel";
import LastReportsTable from "../components/LastReportsTable";
import { getFixtures, getReports, openFixturesStream } from "../api/client";
import { useToast } from "../context/ToastContext";

export default function FixturesPage() {
  const showToast = useToast();
  const [fixtures, setFixtures] = useState([]);
  const [lastReports, setLastReports] = useState([]);
  const [gaugeId, setGaugeId] = useState("");
  const [selectedGaugeId, setSelectedGaugeId] = useState(null);

  const refreshFixtures = useCallback(() => {
    getFixtures()
      .then(setFixtures)
      .catch(() => showToast("Could not refresh fixtures", "error"));
  }, [showToast]);

  const refreshLastReports = useCallback(() => {
    getReports({ limit: 10 })
      .then(setLastReports)
      .catch(() => {});
  }, []);

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

  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, run: 0, idle: 0 };
    fixtures.forEach((f) => {
      if (f.status === "PASS") c.pass++;
      else if (f.status === "FAIL") c.fail++;
      else if (f.status === "RUNNING") c.run++;
      else c.idle++;
    });
    return c;
  }, [fixtures]);

  const selectedFixture = fixtures.find((f) => f.slave_id === selectedGaugeId) || null;

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
            onGaugeIdChange={setGaugeId}
            onStarted={() => {
              refreshFixtures();
              refreshLastReports();
            }}
          />

          <ConveyorTrack fixtures={fixtures} onSelect={handleSelect} />

          {selectedGaugeId && (
            <DetailPanel
              gaugeId={selectedGaugeId}
              fixture={selectedFixture}
              onStopped={() => {
                refreshFixtures();
              }}
            />
          )}
        </div>
      </div>

      <LastReportsTable rows={lastReports} onRowClick={handleRowClick} />
    </>
  );
}
