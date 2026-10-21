// A page's shape while it loads (OPS-8): grey bars where the text will be, so
// the page doesn't jump when it arrives.
export function Skeleton({ lines = 3, title = true }: { lines?: number; title?: boolean }) {
  return (
    <div className="animate-pulse space-y-3" aria-busy="true" aria-label="Уншиж байна">
      {title && <div className="h-7 w-64 rounded-md bg-surface-2" />}
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-4 rounded bg-surface-2" style={{ width: `${90 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  )
}

/** A whole page loading: its title, a block of text and a panel. */
export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton lines={2} />
      <div className="h-48 animate-pulse rounded-xl bg-surface" />
      <Skeleton lines={4} title={false} />
    </div>
  )
}
