// What a page says when its data didn't load (OPS-8): missing, or unreadable
// with a way to try again.
import { errorStatus } from '../api/errors'

export function LoadError(props: { error: unknown; what: string; retry?: () => void }) {
  const { error, what, retry } = props
  const status = errorStatus(error)
  if (status === 404) return <p className="text-crit">{what} олдсонгүй.</p>
  return (
    <p className="text-crit">
      {what} уншиж чадсангүй
      {status ? ` (сервер ${status} алдаа өглөө)` : ' (сүлжээ эсвэл сервер хариу өгсөнгүй)'}.{' '}
      {retry && (
        <button type="button" onClick={retry} className="text-ct underline">
          Дахин оролдох
        </button>
      )}
    </p>
  )
}
