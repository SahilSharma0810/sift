import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TriagePill } from './TriagePill'

describe('TriagePill', () => {
  it('renders the unprocessable variant', () => {
    const { getByText } = render(<TriagePill variant="unprocessable" />)
    expect(getByText('Unprocessable')).toBeInTheDocument()
  })

  it('renders the confident variant', () => {
    const { getByText } = render(<TriagePill variant="confident" />)
    expect(getByText('Confident')).toBeInTheDocument()
  })

  it('renders likely_duplicate as "Likely duplicate"', () => {
    const { getByText } = render(<TriagePill variant="likely_duplicate" />)
    expect(getByText('Likely duplicate')).toBeInTheDocument()
  })
})
