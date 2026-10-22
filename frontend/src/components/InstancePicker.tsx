import type { ReactNode } from 'react'
import ChoiceCards from './ChoiceCards'

/** Asks App to show the settings page — where each repository's tokens and communities live. */
export const OPEN_SETTINGS_EVENT = 'wildintel:open-settings'

type Environment = 'sandbox' | 'production'

/** The "Where to publish" choice of a repository that has a Sandbox and a Production instance: two cards, and under
 * them what the settings already say (community, token) with a link to change it — nothing about the connection is typed here. */
/** The link that opens the settings page, where a repository's connection data lives. */
export function SettingsLink({ repository }: { repository: string }) {
  return (
    <button
      type="button" className="mt-3 font-semibold text-blue-600 dark:text-blue-400 hover:underline"
      onClick={() => window.dispatchEvent(new Event(OPEN_SETTINGS_EVENT))}
    >
      Open the {repository} settings
    </button>
  )
}

export default function InstancePicker({ name, repository, value, onChange, hasToken, communities, communityRequired = false, dryRun = false, credential = 'token', subject }: {
  /** Radio group name. */
  name: string
  /** "Zenodo", "B2SHARE" — for the settings link. */
  repository: string
  value: string
  onChange: (environment: Environment) => void
  hasToken: Record<Environment, boolean>
  /** The community (or comma-separated communities) saved for each instance, if any. */
  communities: Record<string, string | null>
  /** Publishing is not possible without a community (B2SHARE). */
  communityRequired?: boolean
  dryRun?: boolean
  /** What the settings hold for the instance: an access "token" (default) or an "account". */
  credential?: 'token' | 'account'
  /** Replaces the sentence about the community, for a repository that has none (GBIF's organization). */
  subject?: ReactNode
}) {
  const environment = value as Environment
  const label = environment === 'sandbox' ? 'Sandbox' : 'Production'
  const community = communities[environment]
  return (
    <div>
      <ChoiceCards
        name={name} label="Environment" layout="row"
        value={environment}
        onChoose={onChange}
        options={([
          ['sandbox', 'Sandbox', 'Practice. Nothing is public.'],
          ['production', 'Production', 'Real DOI, public and permanent.'],
        ] as const).map(([env, title, description]) => {
          const missing = !dryRun && !hasToken[env]
          return { value: env, title, description: missing ? `Add a ${title} ${credential} first.` : description, disabled: missing }
        })}
      />
      <div className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
        <p>
          {subject ?? (community ? (
            <>
              Published in the {community.includes(',') ? 'communities' : 'community'}{' '}
              <strong className="text-zinc-800 dark:text-zinc-200 break-all">{community}</strong>
            </>
          ) : communityRequired && !dryRun ? (
            <span className="text-amber-600 dark:text-amber-400">No community is saved for {label} yet</span>
          ) : (
            'Not submitted to any community'
          ))}
          {dryRun ? (
            `, and no ${credential} is needed for a practice run.`
          ) : hasToken[environment] ? (
            <>, using the {label} {credential} saved in Settings.</>
          ) : (
            <span className="text-amber-600 dark:text-amber-400">. No {label} {credential} is saved yet.</span>
          )}
        </p>
        <SettingsLink repository={repository} />
      </div>
    </div>
  )
}
