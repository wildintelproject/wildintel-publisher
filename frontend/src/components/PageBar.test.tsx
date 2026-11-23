import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageTitle } from './PageBar'

describe('PageTitle', () => {
  it('shows the title, what the page says and its actions', () => {
    render(<PageTitle title="Unfinished runs" description="Pick one up" actions={<button type="button">Skip</button>} label="Run actions" />)

    expect(screen.getByRole('heading', { level: 1, name: 'Unfinished runs' })).toBeInTheDocument()
    expect(screen.getByText('Pick one up')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Run actions' })).toContainElement(screen.getByRole('button', { name: 'Skip' }))
  })

  it('leaves out the description and the actions when there are none', () => {
    render(<PageTitle title="Only a title" />)

    expect(screen.getByRole('heading', { name: 'Only a title' })).toBeInTheDocument()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })
})
