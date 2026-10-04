import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import SettingsPage from './SettingsPage'
import type { AppSettings } from '../types'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), saveSettings: vi.fn(), clearLog: vi.fn(),
    openConfigFolder: vi.fn(), configs: vi.fn(), addConfig: vi.fn(), activateConfig: vi.fn(), checkVersion: vi.fn(), s3TestConnection: vi.fn() } }))

const mockedApi = vi.mocked(api)

const APP_SETTINGS: AppSettings = {
  GENERAL: { log_level: 'INFO', log_file: '/home/me/.config/wildintel-publisher/logs/wildintel-publisher.log', config_file: '/home/me/.config/wildintel-publisher/settings.toml', log_level_override: null },
  CAMTRAPDP: {
    license_id: 'CC-BY-NC-4.0', license_name: 'Creative Commons Attribution-NonCommercial 4.0 International',
    license_url: 'https://creativecommons.org/licenses/by-nc/4.0/', dataset_slug: 'wildintel-camtrapdp',
    dataset_name: 'Wildintel Camtrapdp', description: null,
  },
  TRAPPER: {
    base_url: 'https://trapper.example.org', has_user_name: true, has_user_password: true, project_id: 12,
    retry_attempts: 3, retry_wait_seconds: 2,
  },
  HFH: {
    message: 'If you use this dataset, please cite it as below.',
    repository_code: 'https://github.com/wildintelproject/wildintel-publisher',
    repo_id: null, username: null, has_token: false,
  },
  ZENODO: {
    environment: 'sandbox', sandbox_communities: null, production_communities: null,
    has_sandbox_token: false, has_production_token: false,
  },
  B2SHARE: {
    environment: 'sandbox', sandbox_community_id: null, production_community_id: null,
    has_sandbox_token: false, has_production_token: false,
  },
  GBIF: {
    environment: 'sandbox', sandbox_publishing_organization_key: null, production_publishing_organization_key: null,
    sandbox_installation_key: null, production_installation_key: null, registry_language: 'eng',
    has_sandbox_username: false, has_sandbox_password: false, has_production_username: false, has_production_password: false,
    installations: [{ title: 'WildINTEL', sandbox_installation_key: 'abc-123', production_installation_key: null }],
  },
  S3: {
    remotes: [{
      id: 'r1', name: 'WildINTEL', endpoint_url: 'https://s3.example.org', region: 'garage', bucket: 'public', prefix: null,
      public_base_url: null, verify_ssl: true, has_access_key: false, has_secret_key: false,
    }],
    retry_attempts: 3, retry_wait_seconds: 2,
  },
  PRODUCT: {
    organizations: [{ title: 'University of Huelva', path: 'https://www.uhu.es/', email: null, gbif_sandbox_organization_key: null, gbif_production_organization_key: null }],
    authors: [{ name: 'Jane Doe', affiliation: 'University of Huelva' }],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getSettings.mockResolvedValue(APP_SETTINGS)
  mockedApi.saveSettings.mockImplementation(async (update) => ({
    GENERAL: { ...APP_SETTINGS.GENERAL, ...update.GENERAL },
    CAMTRAPDP: { ...APP_SETTINGS.CAMTRAPDP, ...update.CAMTRAPDP },
    TRAPPER: { ...APP_SETTINGS.TRAPPER, ...update.TRAPPER, has_user_name: !!update.TRAPPER.user_name, has_user_password: !!update.TRAPPER.user_password },
    HFH: { ...APP_SETTINGS.HFH, ...update.HFH, has_token: !!update.HFH.token },
    ZENODO: { ...APP_SETTINGS.ZENODO, ...update.ZENODO, has_sandbox_token: !!update.ZENODO.sandbox_token, has_production_token: !!update.ZENODO.production_token },
    B2SHARE: { ...APP_SETTINGS.B2SHARE, ...update.B2SHARE, has_sandbox_token: !!update.B2SHARE.sandbox_token, has_production_token: !!update.B2SHARE.production_token },
    GBIF: {
      ...APP_SETTINGS.GBIF, ...update.GBIF,
      has_sandbox_username: !!update.GBIF.sandbox_username, has_sandbox_password: !!update.GBIF.sandbox_password,
      has_production_username: !!update.GBIF.production_username, has_production_password: !!update.GBIF.production_password,
    },
    S3: {
      ...APP_SETTINGS.S3, ...update.S3,
      remotes: update.S3.remotes.map(({ access_key, secret_key, ...r }) => ({ ...r, has_access_key: !!access_key, has_secret_key: !!secret_key })),
    },
    PRODUCT: update.PRODUCT,
  }))
})

const section = (name: string) => userEvent.click(screen.getByRole('button', { name }))

describe('SettingsPage', () => {
  it('shows one section at a time, from the sidebar', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    expect(await screen.findByLabelText('Log level')).toHaveValue('INFO')
    expect(screen.getByRole('button', { name: /General/ })).toHaveAttribute('aria-current', 'page')

    await section('Trapper')
    expect(screen.getByLabelText('URL')).toHaveValue('https://trapper.example.org')
    expect(screen.getByText(/a username is saved — leave it blank to keep it/i)).toBeInTheDocument()
    expect(screen.getByText(/a password is saved — leave it blank to keep it/i)).toBeInTheDocument()

    await section('Repositories')
    expect(screen.queryByLabelText('URL')).not.toBeInTheDocument()
    for (const name of ['HuggingFace Hub', 'Zenodo', 'B2SHARE', 'GBIF']) expect(screen.getByText(name)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Edit HuggingFace Hub' }))
    expect(screen.getByText(/no token saved yet/i)).toBeInTheDocument()

    await section('Organizations')
    expect(screen.getByText('University of Huelva')).toBeInTheDocument()
    expect(screen.getByText('https://www.uhu.es/')).toBeInTheDocument()
  })

  it('saves the Trapper and Camtrap DP sections, a blank password keeping the saved one', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await screen.findByLabelText('Log level')
    await section('Products')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Camtrap DP' }))
    await userEvent.type(screen.getByLabelText('Description'), 'New description')
    await section('Trapper')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockedApi.saveSettings).toHaveBeenCalledOnce()
    const body = mockedApi.saveSettings.mock.calls[0][0]
    expect(body.TRAPPER).toMatchObject({
      base_url: 'https://trapper.example.org', user_name: null, user_password: null,
    })
    expect(body.CAMTRAPDP).toMatchObject({ license_id: 'CC-BY-NC-4.0', description: 'New description' })
    expect(await screen.findByText('Settings saved.')).toBeInTheDocument()
  })

  it('rejects a non-numeric project id and cannot save', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await screen.findByLabelText('Log level')
    await section('Trapper')
    const projectId = screen.getByLabelText('Default classification project id')
    await userEvent.clear(projectId)
    await userEvent.type(projectId, 'abc')
    expect(screen.getByText('A whole number, or blank.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('adds and removes a GBIF installation', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Repositories')
    await userEvent.click(screen.getByRole('button', { name: 'Edit GBIF' }))
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

  it('adds an organization from a dialog, edits another from its gear, and saves them', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Organizations')
    await userEvent.click(screen.getByRole('button', { name: 'Add organization' }))
    await userEvent.clear(screen.getByLabelText('Title'))
    await userEvent.type(screen.getByLabelText('Title'), 'New Org')
    await userEvent.type(screen.getByLabelText('GBIF sandbox organization UUID'), 'abc-123')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.getByText('GBIF linked')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Edit University of Huelva' }))
    await userEvent.type(screen.getByLabelText('Contact email (publisher role only)'), 'a@uhu.es')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    const product = mockedApi.saveSettings.mock.calls[0][0].PRODUCT
    expect(product.organizations.map((o) => o.title)).toEqual(['University of Huelva', 'New Org'])
    expect(product.organizations[0].email).toBe('a@uhu.es')
    expect(product.organizations[1].gbif_sandbox_organization_key).toBe('abc-123')
  })

  it('removes an organization from its dialog', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Organizations')
    await userEvent.click(screen.getByRole('button', { name: 'Edit University of Huelva' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove organization' }))
    expect(screen.queryByText('University of Huelva')).not.toBeInTheDocument()
  })

  const CONFIGS = [
    { id: 'default', name: 'Default config', path: '/home/me/.config/wildintel-publisher/settings.toml', active: true },
  ]

  it('lists the configs with their folder and download buttons', async () => {
    mockedApi.configs.mockResolvedValue(CONFIGS)
    mockedApi.openConfigFolder.mockResolvedValue({ ok: true })
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Config')
    expect(await screen.findByText('ACTIVE')).toBeInTheDocument()
    expect(screen.getByLabelText('Default config file location')).toHaveTextContent('/home/me/.config/wildintel-publisher/settings.toml')
    expect(screen.getByRole('link', { name: 'Download Default config' })).toHaveAttribute('href', '/api/settings/configs/default/download')
    expect(screen.queryByRole('button', { name: 'Activate Default config' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Open Default config folder' }))

    expect(mockedApi.openConfigFolder).toHaveBeenCalledWith('default')
  })

  it('adds a config from the + button, named by the user', async () => {
    mockedApi.configs.mockResolvedValue(CONFIGS)
    mockedApi.addConfig.mockResolvedValue([...CONFIGS, { id: 'project-b', name: 'project-b', path: '/x/configs/project-b.toml', active: false }])
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Config')
    await userEvent.click(await screen.findByRole('button', { name: 'Add config' }))
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Config name'), 'Project B')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(mockedApi.addConfig).toHaveBeenCalledWith('Project B')
    expect(await screen.findByText('project-b')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('switches to another config and reloads the settings from it', async () => {
    const other = { id: 'b', name: 'b', path: '/x/configs/b.toml', active: false }
    mockedApi.configs.mockResolvedValue([...CONFIGS, other])
    mockedApi.activateConfig.mockResolvedValue([{ ...CONFIGS[0], active: false }, { ...other, active: true }])
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Config')
    mockedApi.getSettings.mockClear()
    await userEvent.click(await screen.findByRole('button', { name: 'Activate b' }))

    expect(mockedApi.activateConfig).toHaveBeenCalledWith('b')
    await waitFor(() => expect(mockedApi.getSettings).toHaveBeenCalledOnce())
    expect(screen.queryByRole('button', { name: 'Activate b' })).not.toBeInTheDocument()
  })

  const CHECK = { current: '0.1.0', latest: '0.1.0', update_available: false, release_url: null, download_url: null, error: null }

  it('checks for updates and says when the app is up to date', async () => {
    mockedApi.checkVersion.mockResolvedValue(CHECK)
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check updates' }))

    expect(await screen.findByText(/up to date \(version 0\.1\.0\)/)).toBeInTheDocument()
  })

  it('offers the download when a newer version exists', async () => {
    mockedApi.checkVersion.mockResolvedValue({
      ...CHECK, latest: '0.2.0', update_available: true,
      release_url: 'https://github.com/x/releases/web-v0.2.0', download_url: 'https://dl/app-0.2.0-linux-x86_64',
    })
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check updates' }))

    expect(await screen.findByRole('link', { name: 'Tap to download 0.2.0' })).toHaveAttribute('href', 'https://dl/app-0.2.0-linux-x86_64')
  })

  it('offers a retry when the check fails, and recovers on the next try', async () => {
    mockedApi.checkVersion.mockResolvedValueOnce({ ...CHECK, latest: null, error: 'Could not check for updates: offline' })
    mockedApi.checkVersion.mockResolvedValueOnce(CHECK)
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check updates' }))
    expect(await screen.findByText(/offline/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tap to retry' }))

    expect(await screen.findByText(/up to date/)).toBeInTheDocument()
    expect(screen.queryByText(/offline/)).not.toBeInTheDocument()
  })

  it('adds, edits and saves authors', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Authors')
    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add author' }))
    await userEvent.clear(screen.getByLabelText('Name'))
    await userEvent.type(screen.getByLabelText('Name'), 'John Roe')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Edit Jane Doe' }))
    await userEvent.type(screen.getByLabelText('Affiliation'), ' (Spain)')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    const { authors } = mockedApi.saveSettings.mock.calls[0][0].PRODUCT
    expect(authors).toEqual([
      { name: 'Jane Doe', affiliation: 'University of Huelva (Spain)' },
      { name: 'John Roe', affiliation: null },
    ])
  })

  it('saves the log level, showing where the log is', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    expect(await screen.findByLabelText('Log file location')).toHaveTextContent('wildintel-publisher.log')

    await userEvent.selectOptions(screen.getByLabelText('Log level'), 'DEBUG')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockedApi.saveSettings.mock.calls[0][0].GENERAL).toEqual({ log_level: 'DEBUG' })
    expect(await screen.findByText('Settings saved.')).toBeInTheDocument()
  })

  it('asks before clearing the log', async () => {
    mockedApi.clearLog.mockResolvedValue({ deleted: 2 })
    render(<SettingsPage onClose={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Clear log' }))
    expect(mockedApi.clearLog).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Yes, clear it' }))
    expect(mockedApi.clearLog).toHaveBeenCalledOnce()
    expect(await screen.findByText(/log cleared/i)).toBeInTheDocument()
  })

  it('goes back', async () => {
    const onClose = vi.fn()
    render(<SettingsPage onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('lists the S3 remotes as cards, each edited from its gear button', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('S3 image hosting')
    expect(screen.getByText('WildINTEL')).toBeInTheDocument()
    expect(screen.getByText(/bucket public · https:\/\/s3\.example\.org/)).toBeInTheDocument()
    expect(screen.getByText('No credentials')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Edit WildINTEL' }))
    expect(screen.getByLabelText('Bucket')).toHaveValue('public')
    expect(screen.getByText(/no access key saved yet/i)).toBeInTheDocument()
  })

  it('saves an edited S3 remote, sending an empty prefix/public base URL as a real clear', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('S3 image hosting')
    await userEvent.click(screen.getByRole('button', { name: 'Edit WildINTEL' }))
    await userEvent.clear(screen.getByLabelText('Bucket'))
    await userEvent.type(screen.getByLabelText('Bucket'), 'my-camtrapdp-images')
    await userEvent.type(screen.getByLabelText('Access key'), 'AKIAEXAMPLE')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockedApi.saveSettings).toHaveBeenCalledOnce()
    const [remote] = mockedApi.saveSettings.mock.calls[0][0].S3.remotes
    expect(remote).toMatchObject({
      id: 'r1', name: 'WildINTEL', bucket: 'my-camtrapdp-images', prefix: null, public_base_url: null,
      access_key: 'AKIAEXAMPLE', secret_key: null,
    })
    expect(await screen.findByText('Settings saved.')).toBeInTheDocument()
  })

  it('adds a second S3 remote and removes one', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('S3 image hosting')
    await userEvent.click(screen.getByRole('button', { name: 'Add remote' }))
    await userEvent.clear(screen.getByLabelText('Name'))
    await userEvent.type(screen.getByLabelText('Name'), 'Backup')
    await userEvent.type(screen.getByLabelText('Bucket'), 'backup-bucket')
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.getByText('Backup')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Edit WildINTEL' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove remote' }))
    expect(screen.queryByText('WildINTEL')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    const remotes = mockedApi.saveSettings.mock.calls[0][0].S3.remotes
    expect(remotes.map((r) => [r.name, r.bucket])).toEqual([['Backup', 'backup-bucket']])
  })

  it('tests a remote from its dialog with the form as it is now', async () => {
    mockedApi.s3TestConnection.mockResolvedValue({ ok: true })
    render(<SettingsPage onClose={vi.fn()} />)
    await section('S3 image hosting')
    await userEvent.click(screen.getByRole('button', { name: 'Edit WildINTEL' }))
    await userEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    expect(await screen.findByText(/connection successful/i)).toBeInTheDocument()
    expect(mockedApi.s3TestConnection).toHaveBeenCalledWith(expect.objectContaining({ remoteId: 'r1', bucket: 'public' }))
  })
})
