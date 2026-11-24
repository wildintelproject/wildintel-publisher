import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Navbar from './Navbar'

function renderNavbar(props: Partial<Parameters<typeof Navbar>[0]> = {}) {
  const onHome = vi.fn()
  const onOpenSettings = vi.fn()
  render(<Navbar version="1.2.3" onHome={onHome} onOpenSettings={onOpenSettings} settingsOpen={false} {...props} />)
  return { onHome, onOpenSettings }
}

describe('Navbar', () => {
  it('shows the title, the version and the buttons of the header, in English', () => {
    renderNavbar()

    expect(screen.getByText('WildINTEL Publisher')).toBeInTheDocument()
    expect(screen.getByText('v1.2.3')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /help/i })).toHaveAttribute('title', 'User and developer documentation')
    expect(screen.getByRole('button', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to the welcome screen' })).toBeInTheDocument()
  })

  it('goes home and opens the settings from its buttons', async () => {
    const { onHome, onOpenSettings } = renderNavbar()

    await userEvent.click(screen.getByRole('button', { name: 'Go to the welcome screen' }))
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))

    expect(onHome).toHaveBeenCalledOnce()
    expect(onOpenSettings).toHaveBeenCalledOnce()
  })

  it('switches between the light and the dark mode', async () => {
    renderNavbar()

    await userEvent.click(screen.getByTitle('Switch to light mode'))

    expect(screen.getByTitle('Switch to dark mode')).toBeInTheDocument()
    expect(document.documentElement).not.toHaveClass('dark')
  })
})
