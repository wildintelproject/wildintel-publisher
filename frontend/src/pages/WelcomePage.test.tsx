import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WelcomePage from './WelcomePage'

describe('WelcomePage', () => {
  it('shows the brand title and all four integrations', () => {
    render(<WelcomePage onStart={() => {}} />)

    expect(screen.getByText('WildINTEL Publisher')).toBeInTheDocument()
    expect(screen.getByText('HuggingFace Hub')).toBeInTheDocument()
    expect(screen.getByText('Zenodo')).toBeInTheDocument()
    expect(screen.getByText('B2SHARE (EUDAT)')).toBeInTheDocument()
    expect(screen.getByText('GBIF')).toBeInTheDocument()
  })

  it('calls onStart when the Get Started button is clicked', async () => {
    const onStart = vi.fn()
    render(<WelcomePage onStart={onStart} />)

    await userEvent.click(screen.getByRole('button', { name: /get started/i }))

    expect(onStart).toHaveBeenCalledOnce()
  })
})
