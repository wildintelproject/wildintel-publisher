import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import SettingsPage from './SettingsPage'
import type { AppSettings } from '../types'

vi.mock('../api', () => ({ api: { getSettings: vi.fn(), saveSettings: vi.fn(), clearLog: vi.fn(),
    openConfigFolder: vi.fn(), configs: vi.fn(), addConfig: vi.fn(), activateConfig: vi.fn(), checkVersion: vi.fn(), checkForUpdate: vi.fn(), listReports: vi.fn(), deleteReport: vi.fn(), getReport: vi.fn(), reportUrl: (id: string, f: string) => `/api/reports/${id}/download?format=${f}`, fsPickDirectory: vi.fn(), trapperTestConnection: vi.fn(), s3TestConnection: vi.fn() } }))

const mockedApi = vi.mocked(api)

const APP_SETTINGS: AppSettings = {
  GENERAL: { log_level: 'INFO', log_file: '/home/me/.config/wildintel-publisher/logs/wildintel-publisher.log', config_file: '/home/me/.config/wildintel-publisher/settings.toml', log_level_override: null, reports_dir: null, default_reports_dir: '/home/me/Documents/wildintel-publisher/reports', sessions_dir: null, default_sessions_dir: '/home/me/Documents/wildintel-publisher/sessions' },
  CAMTRAPDP: {
    license_id: 'CC-BY-NC-4.0', license_name: 'Creative Commons Attribution-NonCommercial 4.0 International',
    license_url: 'https://creativecommons.org/licenses/by-nc/4.0/', dataset_slug: 'wildintel-camtrapdp',
    dataset_name: 'Wildintel Camtrapdp', description: null,
  },
  TRAPPER: {
    base_url: 'https://trapper.example.org', user_name: 'jane@example.org', has_user_password: true, project_id: 12,
    download_workers: 4, retry_attempts: 3, retry_wait_seconds: 2,
  },
  HFH: {
    message: 'If you use this dataset, please cite it as below.',
    repository_code: 'https://github.com/wildintelproject/wildintel-publisher',
    repo_id: null, username: null, has_token: false,
  },
  ZENODO: {
    environment: 'sandbox', sandbox_communities: null, production_communities: null,
    max_record_size_gb: 50, max_files: 100, max_file_size_gb: null,
    has_sandbox_token: false, has_production_token: false,
  },
  B2SHARE: {
    environment: 'sandbox', sandbox_community_id: null, production_community_id: null,
    max_record_size_gb: null, max_files: 100, max_file_size_gb: 20,
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
    TRAPPER: { ...APP_SETTINGS.TRAPPER, ...update.TRAPPER, has_user_password: !!update.TRAPPER.user_password },
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
    expect(screen.getByLabelText('Username')).toHaveValue('jane@example.org')
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
      base_url: 'https://trapper.example.org', user_name: 'jane@example.org', user_password: null,
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

  it('saves the number of parallel Trapper downloads', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await screen.findByLabelText('Log level')
    await section('Trapper')
    const workers = screen.getByLabelText('Parallel downloads')
    expect(workers).toHaveValue('4')
    await userEvent.clear(workers)
    await userEvent.type(workers, '8')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockedApi.saveSettings.mock.calls[0][0].TRAPPER).toMatchObject({ download_workers: 8 })
  })

  it.each(['0', '33', 'abc', ''])('rejects %j parallel downloads and cannot save', async (value) => {
    render(<SettingsPage onClose={vi.fn()} />)
    await screen.findByLabelText('Log level')
    await section('Trapper')
    const workers = screen.getByLabelText('Parallel downloads')
    await userEvent.clear(workers)
    if (value) await userEvent.type(workers, value)
    expect(screen.getByText('A whole number from 1 to 32.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('shows and saves the repository limits of Zenodo and B2SHARE, an empty one meaning no limit', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Repositories')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Zenodo' }))
    expect(screen.getByRole('button', { name: /Limits for each record/ })).toHaveTextContent('50 GB in total · 100 files · no limit per file')
    await userEvent.click(screen.getByRole('button', { name: /Limits for each record/ }))
    expect(screen.getByLabelText('Max record size (GB)')).toHaveValue('50')
    expect(screen.getByLabelText('Max files per record')).toHaveValue('100')
    expect(screen.getByLabelText('Max size of one file (GB)')).toHaveValue('')

    await userEvent.clear(screen.getByLabelText('Max record size (GB)'))
    await userEvent.type(screen.getByLabelText('Max size of one file (GB)'), '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Credentials and defaults of the repositories the wizard publishes to.')).toBeInTheDocument()

    const { ZENODO, B2SHARE } = mockedApi.saveSettings.mock.calls[0][0]
    expect([ZENODO.max_record_size_gb, ZENODO.max_files, ZENODO.max_file_size_gb]).toEqual([null, 100, 30])
    expect([B2SHARE.max_record_size_gb, B2SHARE.max_files, B2SHARE.max_file_size_gb]).toEqual([null, 100, 20])
  })

  it('opens a repository as its own page, replacing the list, and Cancel puts back what was there', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Repositories')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Zenodo' }))

    expect(screen.getByRole('heading', { name: 'Set up Zenodo' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Credentials and defaults of the repositories the wizard publishes to.')).not.toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('New community'), 'wildintelproject')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByText('wildintelproject')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(await screen.findByText('Credentials and defaults of the repositories the wizard publishes to.')).toBeInTheDocument()
    expect(mockedApi.saveSettings).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Edit Zenodo' }))
    expect(screen.queryByText('wildintelproject')).not.toBeInTheDocument()
  })

  it('keeps Production off until it has a token', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Repositories')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Zenodo' }))

    expect(screen.getByRole('radio', { name: /Production/ })).toBeDisabled()
    expect(screen.getByText('Add a Production token first.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^Production/ }))
    await userEvent.type(screen.getAllByLabelText('Access token')[1], 'prod-token')
    expect(screen.getByRole('radio', { name: /Production/ })).toBeEnabled()
  })

  it('saves a repository from its own page and goes back to the list', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Repositories')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Zenodo' }))
    await userEvent.type(screen.getByLabelText('New community'), 'wildintelproject')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Credentials and defaults of the repositories the wizard publishes to.')).toBeInTheDocument()
    expect(mockedApi.saveSettings.mock.calls[0][0].ZENODO.sandbox_communities).toBe('wildintelproject')
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

    await userEvent.click(await screen.findByRole('button', { name: 'Edit GBIF' }))
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

  it('tests the Trapper connection with the values typed, a blank password falling back to the saved one', async () => {
    mockedApi.trapperTestConnection.mockResolvedValue({ ok: true, research_projects_count: 3 })
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Trapper')

    await userEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(mockedApi.trapperTestConnection).toHaveBeenCalledWith('https://trapper.example.org', 'jane@example.org', '')
    expect(await screen.findByText('Connected — 3 research project(s) available.')).toBeInTheDocument()
  })

  it('says why the Trapper connection failed', async () => {
    mockedApi.trapperTestConnection.mockRejectedValue(new Error('Invalid credentials'))
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Trapper')

    await userEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument()
  })

  it('saves a reports folder of its own, and goes back to the default with one click', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    const folder = await screen.findByLabelText('Reports folder')
    expect(folder).toHaveValue('')
    expect(folder).toHaveAttribute('placeholder', '/home/me/Documents/wildintel-publisher/reports')

    await userEvent.type(folder, '/data/my-reports')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(mockedApi.saveSettings).toHaveBeenCalled())
    expect(mockedApi.saveSettings.mock.calls.at(-1)![0].GENERAL.reports_dir).toBe('/data/my-reports')

    await userEvent.click(screen.getByRole('button', { name: 'Use the default reports folder' }))
    expect(screen.getByLabelText('Reports folder')).toHaveValue('')
  })

  it('saves a sessions folder of its own and picks it with the native dialog', async () => {
    mockedApi.fsPickDirectory.mockResolvedValue({ path: '/big-disk/sessions' })
    render(<SettingsPage onClose={vi.fn()} />)
    expect(await screen.findByLabelText('Sessions folder')).toHaveValue('')

    await userEvent.click(screen.getByRole('button', { name: 'Browse for the sessions folder' }))
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockedApi.saveSettings).toHaveBeenCalled())
    expect(mockedApi.saveSettings.mock.calls.at(-1)![0].GENERAL).toMatchObject({ reports_dir: null, sessions_dir: '/big-disk/sessions' })
    expect(mockedApi.fsPickDirectory).toHaveBeenCalledWith('/home/me/Documents/wildintel-publisher/sessions', 'Select the folder to keep the sessions in')
  })

  it('refuses a relative reports folder', async () => {
    render(<SettingsPage onClose={vi.fn()} />)
    await userEvent.type(await screen.findByLabelText('Reports folder'), 'relative/folder')

    expect(screen.getByText('An absolute path (or one starting with ~).')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
  })

  it('picks the reports folder with the native dialog', async () => {
    mockedApi.fsPickDirectory.mockResolvedValue({ path: '/picked/reports' })
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Browse for the reports folder' }))

    expect(screen.getByLabelText('Reports folder')).toHaveValue('/picked/reports')
  })

  it('lists the reports, shows one and deletes it', async () => {
    const summary = {
      id: '20261021-101500_publication_ds', kind: 'publication', title: 'Publication of DS', created_at: '2026-10-21T10:15:00+00:00',
      source_dir: '/data/ds', product_type: 'yolo', checked: 1, totals: { entries: 2, ok: 1, failed: 1, warnings: 0 },
    }
    mockedApi.listReports.mockResolvedValue([summary])
    mockedApi.getReport.mockResolvedValue({
      ...summary, parameters: { dry_run: false }, checks: { publication: { label: 'Publication', ok: 1, failed: 1, warnings: 0 } },
      entries: [
        { identifier: 'hfh', check: 'publication', status: 'ok', message: 'Published at https://hf.co/x.' },
        { identifier: 'gbif', check: 'publication', status: 'failed', message: 'boom' },
      ],
    })
    mockedApi.deleteReport.mockResolvedValue({ status: 'ok' })
    render(<SettingsPage onClose={vi.fn()} />)
    await section('Reports')

    expect(await screen.findByText('Publication of DS')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'View' }))
    expect(await screen.findByText('Published at https://hf.co/x.')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete it' }))
    await waitFor(() => expect(mockedApi.deleteReport).toHaveBeenCalledWith(summary.id))
    expect(screen.queryByText('Publication of DS')).not.toBeInTheDocument()
  })

  const CHECK = { current: '0.1.0', latest: '0.1.0', update_available: false, release_url: null, download_url: null, error: null }

  it('shows the app, its version and the help links above the settings', async () => {
    mockedApi.checkVersion.mockResolvedValue({ current: '0.1.0' })
    render(<SettingsPage onClose={vi.fn()} />)

    expect(await screen.findByText('WildINTEL Publisher')).toBeInTheDocument()
    expect(await screen.findByLabelText('Version')).toHaveTextContent('0.1.0')
    expect(screen.getByRole('link', { name: /Documentation/ })).toHaveAttribute('href', 'https://wildintelproject.github.io/wildintel-publisher/')
    expect(screen.getByRole('link', { name: /Report a problem/ }).getAttribute('href')).toContain('wildintel-publisher/issues/new')
  })

  it('checks for updates and says when the app is up to date', async () => {
    mockedApi.checkForUpdate.mockResolvedValue(CHECK)
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check for updates' }))

    expect(await screen.findByText(/up to date \(version 0\.1\.0\)/)).toBeInTheDocument()
  })

  it('offers the download when a newer version exists', async () => {
    mockedApi.checkForUpdate.mockResolvedValue({
      ...CHECK, latest: '0.2.0', update_available: true,
      release_url: 'https://github.com/x/releases/web-v0.2.0', download_url: 'https://dl/app-0.2.0-linux-x86_64',
    })
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check for updates' }))

    expect(await screen.findByRole('link', { name: 'Tap to download 0.2.0' })).toHaveAttribute('href', 'https://dl/app-0.2.0-linux-x86_64')
  })

  it('offers a retry when the check fails, and recovers on the next try', async () => {
    mockedApi.checkForUpdate.mockResolvedValueOnce({ ...CHECK, latest: null, error: 'Could not check for updates: offline' })
    mockedApi.checkForUpdate.mockResolvedValueOnce(CHECK)
    render(<SettingsPage onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Check for updates' }))
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

    expect(mockedApi.saveSettings.mock.calls[0][0].GENERAL).toEqual({ log_level: 'DEBUG', reports_dir: null, sessions_dir: null })
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
