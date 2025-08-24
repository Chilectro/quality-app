import type { ReactNode } from "react";

type Props = {
  title: string;
  value: ReactNode;
  hint?: string;
};

export default function StatCard({ title, value, hint }: Props) {
  return (
    <div className="rounded-2xl p-4 shadow-sm border bg-white">
      <div className="text-sm text-gray-500">{title}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {hint ? <div className="mt-1 text-xs text-gray-400">{hint}</div> : null}
    </div>
  );
}