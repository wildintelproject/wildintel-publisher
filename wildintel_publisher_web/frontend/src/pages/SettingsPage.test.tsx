import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import SettingsPage from './SettingsPage'
import type { AppSettings } from '../types'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), saveSettings: vi.fn() } }))

const mockedApi = vi.mocked(api)

const APP_SETTINGS: AppSettings = {
  TRAPPER: {
    base_url: 'https://trapper.example.org', has_user_name: true, has_user_password: true, project_id: 12,
    license_id: 'CC-BY-NC-4.0', license_name: 'Creative Commons Attribution-NonCommercial 4.0 International',
    license_url: 'https://creativecommons.org/licenses/by-nc/4.0/', dataset_slug: 'wildintel-camtrapdp',
    dataset_name: 'Wildintel Camtrapdp', description: null,
  },
  HFH: {
    message: 'If you use this dataset, please cite it as below.',
    repository_code: 'https://github.com/wildintelproject/wildintel-publisher',
    repo_id: null, username: null, has_token: false,
  },
  ZENODO: { environment: 'sandbox', communities: null, has_token: false },
  B2SHARE: { environment: 'sandbox', community_id: null, has_token: false },
  GBIF: {
    environment: 'sandbox', publishing_organization_key: null, installation_key: null, registry_language: 'eng',
    has_username: false, has_password: false,
    installations: [{ title: 'WildINTEL', sandbox_installation_key: 'abc-123', production_installation_key: null }],
  },
  PRODUCT: {
    organizations: [{ title: 'University of Huelva', path: 'https://www.uhu.es/', email: null, gbif_sandbox_organization_key: null, gbif_production_organization_key: null }],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getSettings.mockResolvedValue(APP_SETTINGS)
  mockedApi.saveSettings.mockImplementation(async (update) => ({
    TRAPPER: { ...APP_SETTINGS.TRAPPER, ...update.TRAPPER, has_user_name: !!update.TRAPPER.user_name, has_user_password: !!update.TRAPPER.user_password },
    HFH: { ...APP_SETTINGS.HFH, ...update.HFH, has_token: !!update.HFH.token },
    ZENODO: { ...APP_SETTINGS.ZENODO, ...update.ZENODO, has_token: !!update.ZENODO.token },
    B2SHARE: { ...APP_SETTINGS.B2SHARE, ...update.B2SHARE, has_token: !!update.B2SHARE.token },
    GBIF: { ...APP_SETTINGS.GBIF, ...update.GBIF, has_username: !!update.GBIF.username, has_password: !!update.GBIF.password },
    PRODUCT: update.PRODUCT,
  }))
})

const section = (name: string) => userEvent.click(screen.getByRole('button', { name }))

describe('SettingsPage', () => {
  it('shows one section at a time, from the sidebar', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    expect(await screen.findByLabelText('Trapper URL')).toHaveValue('https://trapper.example.org')
    expect(screen.getByRole('button', { name: /Trapper/ })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText(/a username is saved — leave it blank to keep it/i)).toBeInTheDocument()
    expect(screen.getByText(/a password is saved — leave it blank to keep it/i)).toBeInTheDocument()

    await section('HuggingFace Hub')
    expect(screen.queryByLabelText('Trapper URL')).not.toBeInTheDocument()
    expect(screen.getByText(/no token saved yet/i)).toBeInTheDocument()

    await section('Organizations')
    expect(screen.getByLabelText('Title')).toHaveValue('University of Huelva')
  })

  it('saves the Trapper section, a blank password keeping the saved one', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await screen.findByLabelText('Trapper URL')
    const desc = screen.getByLabelText('Description')
    await userEvent.type(desc, 'New description')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockedApi.saveSettings).toHaveBeenCalledOnce()
    const body = mockedApi.saveSettings.mock.calls[0][0]
    expect(body.TRAPPER).toMatchObject({
      base_url: 'https://trapper.example.org', user_name: null, user_password: null, description: 'New description',
    })
    expect(await screen.findByText('Settings saved.')).toBeInTheDocument()
  })

  it('rejects a non-numeric project id and cannot save', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    const projectId = await screen.findByLabelText('Default classification project id')
    await userEvent.clear(projectId)
    await userEvent.type(projectId, 'abc')
    expect(screen.getByText('A whole number, or blank.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('adds and removes a GBIF installation', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('GBIF')
    expect(screen.getAllByLabelText('Title')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: '+ Add installation' }))
    expect(screen.getAllByLabelText('Title')).toHaveLength(2)
    await userEvent.type(screen.getAllByLabelText('Title')[1], 'New install')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    const gbif = mockedApi.saveSettings.mock.calls[0][0].GBIF
    expect(gbif.installations.map((i) => i.title)).toEqual(['WildINTEL', 'New install'])

    await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0])
    expect(screen.getAllByLabelText('Title')).toHaveLength(1)
  })

  it('adds an organization and saves it', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Organizations')
    await userEvent.click(screen.getByRole('button', { name: '+ Add organization' }))
    const titles = screen.getAllByLabelText('Title')
    await userEvent.type(titles[1], 'New Org')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    const product = mockedApi.saveSettings.mock.calls[0][0].PRODUCT
    expect(product.organizations.map((o) => o.title)).toEqual(['University of Huelva', 'New Org'])
  })

  it('goes back', async () => {
    const onClose = vi.fn()
    render(<SettingsPage onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: '← Back' }))
    expect(onClose).toHaveBeenCalled()
  })
})
