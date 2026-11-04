import { useCallback, useEffect, useRef } from "react";

type Props = {
  timestamps: number[];
  selectedTimestamp: number | null;
  onSelectTimestamp: (t: number) => void;
};

export function TimestampSlider({ timestamps, selectedTimestamp, onSelectTimestamp }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const currentIndex = selectedTimestamp !== null ? timestamps.indexOf(selectedTimestamp) : -1;

  const navigate = useCallback(
    (delta: number) => {
      if (timestamps.length === 0) return;
      let next = currentIndex + delta;
      if (next < 0) next = 0;
      if (next >= timestamps.length) next = timestamps.length - 1;
      onSelectTimestamp(timestamps[next]);
    },
    [timestamps, currentIndex, onSelectTimestamp]
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigate(-1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        navigate(1);
      } else if (e.key === "Home") {
        e.preventDefault();
        if (timestamps.length > 0) onSelectTimestamp(timestamps[0]);
      } else if (e.key === "End") {
        e.preventDefault();
        if (timestamps.length > 0) onSelectTimestamp(timestamps[timestamps.length - 1]);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate, timestamps, onSelectTimestamp]);

  if (timestamps.length === 0) return null;

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 0",
      }}
    >
      <button
        className="btn btn-ghost"
        style={{ padding: "2px 8px", fontSize: 14, lineHeight: 1 }}
        onClick={() => navigate(-1)}
        disabled={currentIndex <= 0}
      >
        &larr;
      </button>

      <input
        type="range"
        min={0}
        max={timestamps.length - 1}
        value={currentIndex >= 0 ? currentIndex : 0}
        onChange={(e) => onSelectTimestamp(timestamps[Number(e.target.value)])}
        style={{ flex: 1, accentColor: "#14b8a6" }}
      />

      <button
        className="btn btn-ghost"
        style={{ padding: "2px 8px", fontSize: 14, lineHeight: 1 }}
        onClick={() => navigate(1)}
        disabled={currentIndex >= timestamps.length - 1}
      >
        &rarr;
      </button>

      <span
        style={{
          fontFamily: "monospace",
          fontSize: 11,
          color: "var(--text-dim)",
          minWidth: 100,
          textAlign: "right",
        }}
      >
        {selectedTimestamp !== null ? (
          <>
            t={selectedTimestamp}{" "}
            <span style={{ color: "var(--text-dim)", fontSize: 10 }}>
              ({currentIndex + 1}/{timestamps.length})
            </span>
          </>
        ) : (
          "Select a tick"
        )}
      </span>
    </div>
  );
}
