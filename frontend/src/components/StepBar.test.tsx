import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import StepBar from './StepBar'

const LABELS = ['Product Type', 'Source', 'Metadata', 'Package', 'Publish']

describe('StepBar', () => {
  it('numbers the steps and names them in order', () => {
    render(<StepBar labels={LABELS} current={0} />)

    const items = screen.getAllByRole('listitem')
    expect(items.map((li) => li.textContent?.replace('›', ''))).toEqual(['01Product Type', '02Source', '03Metadata', '04Package', '05Publish'])
  })

  it('marks only the current step', () => {
    render(<StepBar labels={LABELS} current={2} />)

    const current = screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-current') === 'step')
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveTextContent('Metadata')
  })

  it('has one step fewer when one is left out', () => {
    render(<StepBar labels={LABELS.filter((l) => l !== 'Package')} current={3} />)

    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText('04')).toBeInTheDocument()
  })
})
