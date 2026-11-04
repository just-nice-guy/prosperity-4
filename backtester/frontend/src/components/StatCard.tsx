type StatCardProps = {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative";
};

export function StatCard({ label, value, tone = "default" }: StatCardProps) {
  return (
    <div className={`stat-card${tone !== "default" ? ` stat-card-${tone}` : ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}
