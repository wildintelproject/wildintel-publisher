import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LanguageButton from './LanguageButton'
import { LANGUAGES } from '../i18n'

describe('LanguageButton', () => {
  it('offers only English for now, which is the default', async () => {
    expect(LANGUAGES).toEqual([{ code: 'en', name: 'English' }])
    render(<LanguageButton />)

    const button = screen.getByRole('button', { name: 'Language' })
    expect(button).toHaveTextContent('en')
    expect(document.documentElement.lang).toBe('en')

    await userEvent.click(button)

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveTextContent('English')
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('closes the list when a language is chosen or Escape is pressed', async () => {
    render(<LanguageButton />)

    await userEvent.click(screen.getByRole('button', { name: 'Language' }))
    await userEvent.click(screen.getByRole('option', { name: /English/ }))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Language' }))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
