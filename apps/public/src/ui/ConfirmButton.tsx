// A delete that can't be undone asks once more in place: the first click turns
// the button into «Тийм, устгах» beside «Болих». No browser dialog.
import { useState, type ReactNode } from 'react'

export default function ConfirmButton(props: { onConfirm: () => void; className?: string; children: ReactNode }) {
  const [asking, setAsking] = useState(false)
  if (!asking)
    return (
      <button type="button" onClick={() => setAsking(true)} className={props.className}>
        {props.children}
      </button>
    )
  return (
    <span className="inline-flex items-center gap-3">
      <button type="button" onClick={props.onConfirm} className="font-medium text-crit underline">
        Тийм, устгах
      </button>
      <button type="button" onClick={() => setAsking(false)} className="text-ink-3 hover:text-ink">
        Болих
      </button>
    </span>
  )
}
