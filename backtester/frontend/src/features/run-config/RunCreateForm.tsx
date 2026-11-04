import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { apiFetch } from "../../api/client";
import { DatasetInfo, RunRecord } from "../../api/types";

type RunCreateFormProps = {
  datasets: DatasetInfo[];
};

export function RunCreateForm({ datasets }: RunCreateFormProps) {
  const queryClient = useQueryClient();
  const defaultSelection = useMemo(
    () => datasets.slice(0, 2).map((item) => `${item.round_num}:${item.day_num}`),
    [datasets]
  );
  const [traderPath, setTraderPath] = useState("");
  const [selectedDays, setSelectedDays] = useState<string[]>(defaultSelection);

  const createRun = useMutation({
    mutationFn: async () => {
      return apiFetch<RunRecord>("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          trader_path: traderPath,
          round_days: selectedDays.map((value) => {
            const [roundNum, dayNum] = value.split(":").map(Number);
            return { round_num: roundNum, day_num: dayNum };
          })
        })
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createRun.mutate();
  };

  return (
    <form className="stack gap-16" onSubmit={submit}>
      <label className="field">
        <span>Trader path</span>
        <input
          placeholder="C:\\Users\\user\\Prosperity4\\prosperity4\\stage0\\trader.py"
          value={traderPath}
          onChange={(event) => setTraderPath(event.target.value)}
          required
        />
      </label>

      <fieldset className="field">
        <span>Datasets</span>
        <div className="checkbox-grid">
          {datasets.map((dataset) => {
            const value = `${dataset.round_num}:${dataset.day_num}`;
            const checked = selectedDays.includes(value);
            return (
              <label key={value} className="checkbox-card">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => {
                    setSelectedDays((current) =>
                      event.target.checked
                        ? [...current, value]
                        : current.filter((item) => item !== value)
                    );
                  }}
                />
                <div>
                  <strong>Round {dataset.round_num}</strong>
                  <span>Day {dataset.day_num}</span>
                </div>
              </label>
            );
          })}
        </div>
      </fieldset>

      <button className="primary-button" type="submit" disabled={createRun.isPending}>
        {createRun.isPending ? "Launching..." : "Launch local run"}
      </button>

      {createRun.isError ? (
        <p className="error-text">{String(createRun.error)}</p>
      ) : null}
    </form>
  );
}
