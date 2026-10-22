import { useEffect, useState } from 'react'
import { api } from '../api'
import ChoiceCards from './ChoiceCards'
import { LockedChoice, Section } from './FormSection'
import { SettingsLink } from './InstancePicker'
import { preparedCoreFiles } from '../productFiles'
import type { OutputMode, ProductType, Publication } from '../types'

const inputClass = 'w-full px-3 py-2 text-sm rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono'
const labelClass = 'block text-sm font-semibold mb-1.5 text-zinc-700 dark:text-zinc-300'
const hintClass = 'text-xs text-zinc-500 dark:text-zinc-400 mt-1'
const btnOutline = 'px-4 py-2 text-sm border border-zinc-400 dark:border-zinc-500 text-zinc-700 dark:text-zinc-300 rounded hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors disabled:opacity-50 flex items-center gap-2'
const btnPrimary = 'px-6 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'

function SmallSpinner() {
  return <div className="w-4 h-4 border border-zinc-500 border-t-zinc-200 rounded-full animate-spin" />
}

/** Everything HFHPublishForm collects — handed to the wizard via
 * onConfigured, and later replayed by the wizard's own execution runner
 * (see WizardPage's runPublishSequence) to actually call
 * api.hfhStartPublish once every selected repository has been configured. */
export interface HfhPublishConfig {
  repoId: string
  token: string
  priv: boolean
  mirrorImages: boolean
  outputMode: OutputMode
  outputDir: string
}

interface Props {
  /** Which product is being published — an AI Dataset ('yolo') has no
   * Mirror/Link choice (see the Mode section below). */
  productType?: ProductType | null
  /** metadata.json's title (see product.missing_required_fields), used to
   * prefill the repository name field — slugified (lowercased, spaces
   * stripped) since it's what's read as-is from the product. */
  productTitle?: string
  /** metadata.json's version — sent along with "Test token" so the backend
   * can warn if it was already published to this repo (a tag with that
   * name would already exist; see services.hfh_service.test_token). Actual
   * publishing enforces this for real regardless (hfh.upload_to_huggingface's
   * own check) — this is just an early heads-up. */
  productVersion?: string
  /** No repo_id/token is required, and "Test token" is pointless, when the
   * whole publish is a simulation (see WizardPage's dryRun) — nothing is
   * ever actually sent to Hugging Face Hub. */
  dryRun?: boolean
  /** Reports this form's current output directory whenever it changes, so a
   * later step in the publish order can use it as its own inputDir. */
  onOutputDirChange?: (dir: string) => void
  /** A previously-collected config for this same repository — given when
   * the user goes Back to re-visit a step they already configured (see
   * WizardPage's Back button in the "configuring one repository at a time"
   * screen). Seeds every field from it instead of settings.toml/blank, so
   * going back doesn't throw away what was already typed. */
  initialConfig?: HfhPublishConfig
  /** Renders a "Back to X" button next to Continue, at the same height,
   * instead of Continue alone — omitted for the first repository in the
   * publish order (see WizardPage), which has nothing to go back to. */
  onBack?: () => void
  backLabel?: string
  /** Text of the button that confirms this form. */
  continueLabel?: string
  /** Called once the user confirms this repository's configuration is
   * complete — the wizard collects one of these per selected repository
   * before actually publishing anything (see WizardPage). */
  /** New dataset vs. new version (see PublicationKindPicker): a new
   * version pre-fills the previous version's own repository; a new dataset
   * gets a warning if the repository typed in already exists. */
  publication?: Publication | null
  onConfigured: (config: HfhPublishConfig) => void
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'warning' | 'error'

function slugifyRepoName(title: string): string {
  return title.toLowerCase().replace(/\s+/g, '')
}

export default function HFHPublishForm({ productType, publication, productTitle, productVersion, dryRun, onOutputDirChange, initialConfig, onBack, backLabel, continueLabel = 'Continue', onConfigured }: Props) {
  const found = publication?.kind === 'version' ? publication.previous?.hfh ?? null : null
  const [form, setForm] = useState(() => {
    if (!initialConfig) {
      const [hfUser, repoName] = found ? found.repo_id.split('/') : ['', '']
      return { outputDir: '', hfUser: hfUser ?? '', repoName: repoName ?? '' }
    }
    const [hfUser, repoName] = initialConfig.repoId.split('/')
    return { outputDir: initialConfig.outputDir, hfUser: hfUser ?? '', repoName: repoName ?? '' }
  })
  const [mirrorImages, setMirrorImages] = useState(productType === 'yolo' || (initialConfig?.mirrorImages ?? true))
  const [outputMode, setOutputMode] = useState<OutputMode>(initialConfig?.outputMode ?? 'passthrough')
  const [priv, setPriv] = useState(initialConfig?.priv ?? false)
  const [hasSavedToken, setHasSavedToken] = useState(false)

  const repoId = form.hfUser && form.repoName ? `${form.hfUser}/${form.repoName}` : ''

  // A "new dataset" going to a repository that already exists would really
  // publish a new version on top of someone else's (or an earlier) dataset.
  const [existingRepo, setExistingRepo] = useState<string | null>(null)
  useEffect(() => {
    setExistingRepo(null)
    if (publication?.kind !== 'new' || !repoId) return
    let cancelled = false
    const handle = setTimeout(() => {
      api.hfhRepoExists(repoId)
        .then((r) => { if (!cancelled && r.exists) setExistingRepo(repoId) })
        .catch(() => { /* just no warning */ })
    }, 400)
    return () => { cancelled = true; clearTimeout(handle) }
  }, [repoId, publication?.kind])

  // Prefill the username/org from settings.toml — the same file 'hfh
  // config' reads/writes on the CLI. Only the username is remembered
  // across products (see services.hfh_service.save_config): the dataset
  // name itself comes from the product's own title (see the effect below),
  // not from whatever was last used. The token itself is never sent to the
  // frontend; leaving the token field blank later reuses whatever is
  // already saved. Form fields are left alone when initialConfig is given
  // (going Back) — those values are already known-good, no need to
  // re-fetch them. hasSavedToken is fetched regardless, though: it isn't a
  // form field the user could have typed over, and going Back with an
  // initialConfig whose own token was left blank (relying on the saved
  // one) would otherwise leave canContinue permanently false — the
  // Continue button stuck disabled with no way to re-enable it short of
  // typing a token that was never needed in the first place.
  useEffect(() => {
    api.hfhGetConfig()
      .then((config) => {
        setHasSavedToken(config.has_token)
        if (initialConfig) return
        setForm((f) => ({
          ...f,
          outputDir: config.output_dir,
          hfUser: f.hfUser || config.username || '',
        }))
      })
      .catch(() => {})
  }, [initialConfig])

  // Prefill the repository name from the product's own title — only if the
  // user hasn't already typed something in that field.
  useEffect(() => {
    if (!productTitle) return
    setForm((f) => (f.repoName ? f : { ...f, repoName: slugifyRepoName(productTitle) }))
  }, [productTitle])

  // Deliberately depends only on form.outputDir, not onOutputDirChange: the
  // parent passes a fresh inline function on every render, so including it
  // here would refire this effect (and the parent setState it triggers) on
  // every render, looping forever.
  useEffect(() => {
    onOutputDirChange?.(form.outputDir)
  }, [form.outputDir])

  function setField(key: keyof typeof form, value: string) {
    // hfUser/repoName are each just ONE path segment of the final repo_id
    // (built below as `${hfUser}/${repoName}`) — stripping any '/' here
    // stops a pasted full "namespace/repo" id (e.g. someone copying an
    // existing HFH URL) from silently doubling the namespace into
    // 'namespace/namespace/repo', which HFH's own repo_id validation
    // rejects ("Repo id must be in the form 'repo_name' or
    // 'namespace/repo_name'").
    const sanitized = key === 'hfUser' || key === 'repoName' ? value.replace(/\//g, '') : value
    setForm((f) => ({ ...f, [key]: sanitized }))
  }

  const canContinue = dryRun
    ? form.outputDir !== ''
    : repoId !== '' && form.outputDir !== '' && hasSavedToken

  function handleContinue() {
    onConfigured({ repoId, token: '', priv, mirrorImages, outputMode, outputDir: form.outputDir })
  }

  return (
    <div>
      <Section title="Where to publish">
      <div className="grid grid-cols-2 gap-4 mb-1.5">
        <div>
          <label className={labelClass} htmlFor="hfh-user">User or organization</label>
          <input
            id="hfh-user"
            className={inputClass}
            placeholder="user_or_org"
            value={form.hfUser}
            onChange={(e) => setField('hfUser', e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="hfh-repo-name">Repository name</label>
          <input
            id="hfh-repo-name"
            className={inputClass}
            placeholder="dataset"
            value={form.repoName}
            onChange={(e) => setField('repoName', e.target.value)}
          />
        </div>
      </div>
      {found && repoId === found.repo_id && (
        <p className={hintClass}>
          New version of <span className="font-mono">{found.repo_id}</span>
          {found.version && <> — its last version is <span className="font-mono">{found.version}</span></>}.
        </p>
      )}
      {found && repoId !== found.repo_id && (
        <p className="text-sm text-amber-600 dark:text-amber-400">
          ⚠ The previous version is in <span className="font-mono">{found.repo_id}</span> — publishing to another
          repository won't be linked to it.
        </p>
      )}
      {publication?.kind === 'version' && !found && (
        <p className={hintClass}>
          No Hugging Face Hub dataset was found for the previous version — this creates its first one.
        </p>
      )}
      {existingRepo && existingRepo === repoId && (
        <p className="text-sm text-amber-600 dark:text-amber-400">
          ⚠ <span className="font-mono">{repoId}</span> already exists. For a new version of it, go back to the
          metadata step and choose "A new version of an already published dataset" — or pick another name.
        </p>
      )}
      <p className={hintClass + ' mb-4'}>
        {repoId
          ? <>The repository identifier will be: <span className="font-mono">{repoId}</span></>
          : <>Just the name, not the full <span className="font-mono">user/repo</span> id — that's built automatically from both fields above.</>}
      </p>

      <div className="flex items-center gap-6 mb-4">
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} />
          Create as private
        </label>
      </div>

      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {dryRun ? (
          'No token is needed for a practice run.'
        ) : hasSavedToken ? (
          'Published with the Hugging Face Hub token saved in Settings.'
        ) : (
          <span className="text-amber-600 dark:text-amber-400">No Hugging Face Hub token is saved yet.</span>
        )}
      </p>
      <SettingsLink repository="Hugging Face Hub" />
      </Section>

      <Section title="What gets uploaded">
        {productType === 'yolo' ? (
          <LockedChoice
            title="Images and labels, in full."
            description="Linking to the images isn't available because they are local files with no other host."
          />
        ) : (
          <ChoiceCards
            name="hfh-mode" label="What gets uploaded" layout="row"
            value={mirrorImages ? 'self-contained' : 'link'}
            onChoose={(mode) => setMirrorImages(mode === 'self-contained')}
            options={[
              { value: 'self-contained', title: 'Self-contained', description: 'Downloads the images and re-uploads them to Hugging Face Hub, rewriting media.csv to point to them.' },
              { value: 'link', title: 'Link', description: "The repository stores links to where the product's images already live, instead of a copy; media.csv keeps pointing at the original file locations." },
            ]}
          />
        )}
      </Section>

      <Section title="What you get back when it finishes" hint="The next repository starts from this.">
        <ChoiceCards
          name="hfh-output-mode" label="What you get back when it finishes" layout="row"
          value={outputMode}
          onChoose={setOutputMode}
          options={[
            {
              value: 'prepared', title: 'Prepared package',
              description: `Just ${preparedCoreFiles(productType).what} with the changes made while preparing and uploading, plus CITATION.cff/README.md/checksums (needed to sync a DOI/PID here later) — no LICENSE, ${preparedCoreFiles(productType).imagesSeparate ? 'images or the local zip' : 'or the local zip'}.`,
            },
            { value: 'passthrough', title: 'Unchanged copy', description: 'Exactly what you started with, unchanged.' },
          ]}
        />
      </Section>

      <div className="flex justify-between items-start">
        {onBack && (
          <button type="button" className={btnOutline} onClick={onBack}>
            {backLabel ?? '← Back'}
          </button>
        )}
        <button type="button" className={`${btnOutline} ml-auto`} disabled={!canContinue} onClick={handleContinue}>
          {continueLabel}<span aria-hidden="true"> →</span>
        </button>
      </div>
    </div>
  )
}
