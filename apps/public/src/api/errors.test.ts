import { describe, expect, it } from 'vitest'
import { errorText } from './errors'

describe('errorText', () => {
  it("says a string detail as it is", () => {
    expect(errorText({ detail: 'Ийм Strat алга.' })).toBe('Ийм Strat алга.')
  })

  it("joins a 422's messages, without pydantic's prefix", () => {
    const e = {
      detail: [
        { type: 'too_long', loc: ['body', 'maps', 0, 'picks'], msg: 'List should have at most 40 items' },
        { type: 'value_error', loc: ['body', 'title'], msg: 'Value error, title is empty' },
      ],
    }
    expect(errorText(e)).toBe('List should have at most 40 items title is empty')
  })

  it('says nothing when there is no error', () => {
    expect(errorText(null)).toBe('')
    expect(errorText(undefined)).toBe('')
    expect(errorText({ status: 500 })).toBe('')
  })
})
