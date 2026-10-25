import { PILL, STATUS_MN } from './format'

export default function StatusPill({ status, labels = STATUS_MN }: {
  status: string
  labels?: Record<string, string>
}) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${PILL[status] ?? PILL.queued}`}>
      {labels[status] ?? status}
    </span>
  )
}
