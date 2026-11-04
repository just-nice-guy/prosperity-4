type LogsPanelProps = {
  sandbox: string;
  decisionTrace: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
};

export function LogsPanel({ sandbox, decisionTrace, events }: LogsPanelProps) {
  return (
    <div className="stack gap-12">
      <div className="code-block">
        <div className="code-block-title">Sandbox output</div>
        <pre>{sandbox || "No sandbox output."}</pre>
      </div>
      <div className="two-col">
        <div className="code-block">
          <div className="code-block-title">Decision trace</div>
          <pre>{JSON.stringify(decisionTrace.slice(0, 8), null, 2)}</pre>
        </div>
        <div className="code-block">
          <div className="code-block-title">Events</div>
          <pre>{JSON.stringify(events.slice(0, 12), null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
