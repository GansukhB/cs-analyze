export default function Count({ n, label }: { n: number | string; label: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-4 py-2 font-mono text-xs text-ink-3">
      <b className="block font-sans text-xl text-ink">{n}</b>
      {label}
    </div>
  )
}
