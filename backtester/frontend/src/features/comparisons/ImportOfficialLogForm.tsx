import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../../api/client";
import { ComparisonRecord } from "../../api/types";

type ImportOfficialLogFormProps = {
  runId: string;
};

export function ImportOfficialLogForm({ runId }: ImportOfficialLogFormProps) {
  const navigate = useNavigate();
  const [label, setLabel] = useState("official-log");
  const [text, setText] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch<ComparisonRecord>("/api/imports/official-log", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, label, text })
      }),
    onSuccess: (comparison) => {
      navigate(`/comparison/${comparison.comparison_id}`);
    }
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <form className="stack gap-12" onSubmit={onSubmit}>
      <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
        Paste a Prosperity submission log to compare local simulation results against official fills.
      </p>
      <label className="field">
        <span className="field-label">Label</span>
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <label className="field">
        <span className="field-label">Official log</span>
        <textarea
          rows={7}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste a Prosperity submission log here…"
        />
      </label>
      <button className="btn btn-secondary" type="submit" disabled={mutation.isPending || !text.trim()}>
        {mutation.isPending ? "Importing…" : "Create comparison"}
      </button>
      {mutation.isError && <p className="error-text">{String(mutation.error)}</p>}
    </form>
  );
}
