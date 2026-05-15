import { useEffect, useReducer, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { SiftMark } from '@/components/primitives/SiftMark'
import { useLoginMutation } from '@/state/auth'

const ARROW_PATH = 'M5 12h14M12 5l7 7-7 7'

function ArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={ARROW_PATH} />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 3l18 18M10.6 6.1A10 10 0 0 1 12 6c7 0 11 6 11 6a17 17 0 0 1-3 3.6M6.6 6.6A17 17 0 0 0 1 12s4 6 11 6c1.4 0 2.7-.2 3.9-.6M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </svg>
  )
}

type PreviewRowProps = {
  variant: 'confident' | 'review' | 'duplicate'
  label: string
  vendor: string
  amount: string
  reason: string
}

function PreviewRow({ variant, label, vendor, amount, reason }: PreviewRowProps) {

  const pillTone = {
    confident: 'text-aside-confident border-aside-confident-ring bg-aside-confident-tint',
    review: 'text-aside-review border-aside-review-ring bg-aside-review-tint',
    duplicate:
      'text-aside-duplicate border-aside-duplicate-ring bg-aside-duplicate-tint',
  }[variant]

  const dotColor = {
    confident: 'bg-aside-confident',
    review: 'bg-aside-review',
    duplicate: 'bg-aside-duplicate',
  }[variant]

  return (
    <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3.5 text-[13px] text-light-muted">
      <span
        className={`inline-flex items-center gap-1.5 border px-2 py-0.5 text-[11.5px] leading-[18px] whitespace-nowrap ${pillTone}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
        {label}
      </span>
      <span className="font-medium tracking-[-0.005em] text-light">{vendor}</span>
      <span className="font-mono text-light">{amount}</span>
      <span className="font-mono text-[11.5px] text-light-subtle">{reason}</span>
    </div>
  )
}

interface FormState {
  email: string
  password: string
  showPassword: boolean
  remember: boolean
  errorMessage: string | null
}

type FormAction =
  | { type: 'setEmail'; value: string }
  | { type: 'setPassword'; value: string }
  | { type: 'toggleShowPassword' }
  | { type: 'setRemember'; value: boolean }
  | { type: 'setError'; value: string | null }

function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case 'setEmail':
      return { ...state, email: action.value }
    case 'setPassword':
      return { ...state, password: action.value }
    case 'toggleShowPassword':
      return { ...state, showPassword: !state.showPassword }
    case 'setRemember':
      return { ...state, remember: action.value }
    case 'setError':
      return { ...state, errorMessage: action.value }
  }
}

const INITIAL_FORM: FormState = {
  email: '',
  password: '',
  showPassword: false,
  remember: true,
  errorMessage: null,
}

export function LoginScreen() {
  const navigate = useNavigate()
  const loginMutation = useLoginMutation()
  const [form, dispatch] = useReducer(formReducer, INITIAL_FORM)
  const { email, password, showPassword, remember, errorMessage } = form

  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    if (!meta) return
    const original = meta.content
    meta.content = 'width=device-width, initial-scale=1'
    return () => {
      meta.content = original
    }
  }, [])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!email.trim() || !password) return
    dispatch({ type: 'setError', value: null })
    loginMutation.mutate(
      { email: email.trim(), password, remember },
      {
        onSuccess: () => {
          navigate('/inbox', { replace: true })
        },
        onError: (err) => {
          const detail =
            err.status === 401
              ? 'Email or password incorrect.'
              : 'Something went wrong. Try again.'
          dispatch({ type: 'setError', value: detail })
        },
      },
    )
  }

  return (
    <div className="grid h-screen grid-cols-1 overflow-hidden bg-canvas md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] md:grid-rows-1 max-md:grid-rows-[auto_1fr]">
      {}
      {}
      <aside
        className={[
          'relative flex flex-col overflow-hidden bg-tile text-light',
          'px-5 py-3.5 md:p-14 md:px-16',

          "after:pointer-events-none after:absolute after:-right-[120px] after:-bottom-[160px]",
          'after:h-[460px] after:w-[460px] after:bg-aside-glow after:content-[""]',
        ].join(' ')}
      >
        <div className="flex items-center gap-2.5">
          <SiftMark size={28} dark className="shrink-0" />
          <div className="text-[17px] font-bold leading-none tracking-[-0.04em] text-light">
            Sift<span className="text-action-light">.</span>
          </div>
          <div className="ml-auto font-mono text-[11px] tracking-[0.04em] text-light-subtle">
            v0.4
          </div>
        </div>

        <div className="mt-auto mb-8 max-md:hidden">
          <div className="mb-[18px] text-[11px] font-medium uppercase tracking-[0.12em] text-light-subtle">
            Accounts payable, reimagined
          </div>
          <h1 className="m-0 max-w-[18ch] text-balance text-[44px] font-semibold leading-[1.06] tracking-[-0.024em] text-light">
            Structured data <br />
            from messy invoices.
          </h1>
          <p className="mt-[18px] max-w-[38ch] text-[16px] leading-[1.5] tracking-[-0.005em] text-light-muted">
            Sift extracts vendor invoices, scores every field with composite
            confidence, and triages your inbox so you spend attention only
            where it actually matters.
          </p>

          <div
            aria-hidden="true"
            className="mt-7 flex max-w-[440px] flex-col gap-3 border border-hairline-dark bg-white/[0.04] p-4"
          >
            <PreviewRow
              variant="confident"
              label="Confident"
              vendor="Vega Logistics"
              amount="USD 1,180.00"
              reason="auto-approved"
            />
            <PreviewRow
              variant="review"
              label="Needs review"
              vendor="Acme Freight"
              amount="USD 4,860.00"
              reason="off $0.40"
            />
            <PreviewRow
              variant="duplicate"
              label="Duplicate"
              vendor="Bramble Coffee Co."
              amount="USD 453.20"
              reason="98% match"
            />
          </div>
        </div>

        <div className="mt-8 flex items-center border-t border-hairline-dark pt-[22px] text-[12px] text-light-subtle max-md:hidden">
          <span>© 2026 Sift Labs</span>
        </div>
      </aside>

      <main className="flex flex-col overflow-y-auto bg-canvas px-5 py-6 md:px-14 md:py-8">
        <div className="flex items-center gap-3.5 text-[13px] text-ink-60">
          <span>New here?</span>
          <button type="button" className="font-medium text-action hover:underline">
            Request access
          </button>
        </div>

        <div className="my-auto w-full max-w-[380px] py-6 md:py-14">
          <h2 className="m-0 mb-1.5 text-balance text-[30px] font-semibold tracking-[-0.02em] text-ink">
            Sign in to Sift
          </h2>
          <p className="m-0 text-[15px] leading-[1.5] tracking-[-0.005em] text-ink-60">
            Welcome back. Use your work email and password to continue.
          </p>

          <form onSubmit={handleSubmit} className="mt-7">

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="email"
                className="text-[12px] font-medium tracking-[-0.005em] text-ink-60"
              >
                Work email
              </label>
              <input
                id="email"
                type="email"
                required
                placeholder="ap-clerk@yourcompany.com"
                autoComplete="username"
                spellCheck={false}
                value={email}
                onChange={(e) => dispatch({ type: 'setEmail', value: e.target.value })}

                className="block w-full rounded-none border border-hairline bg-surface px-3.5 py-2.5 font-sans text-[14.5px] text-ink transition-colors placeholder:text-ink-48 hover:border-ink-48 focus:border-action focus:outline-none focus:ring-[3px] focus:ring-action/[0.14] max-md:px-4 max-md:py-3.5 max-md:text-base"
              />
            </div>

            <div className="mt-3.5 flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <label
                  htmlFor="password"
                  className="text-[12px] font-medium tracking-[-0.005em] text-ink-60"
                >
                  Password
                </label>
                <button
                  type="button"
                  className="text-[12px] font-medium text-action hover:underline"
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative block w-full">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => dispatch({ type: 'setPassword', value: e.target.value })}
                  className="block w-full rounded-none border border-hairline bg-surface py-2.5 pl-3.5 pr-11 font-sans text-[14.5px] text-ink transition-colors placeholder:text-ink-48 hover:border-ink-48 focus:border-action focus:outline-none focus:ring-[3px] focus:ring-action/[0.14] max-md:py-3.5 max-md:pl-4 max-md:pr-[52px] max-md:text-base"
                />
                <button
                  type="button"
                  onClick={() => dispatch({ type: 'toggleShowPassword' })}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}

                  className="absolute inset-y-0 right-1 my-auto grid size-9 cursor-pointer place-items-center border-0 bg-transparent text-ink-48 transition-colors duration-100 hover:text-ink max-md:size-11"
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
            </div>

            {errorMessage ? (
              <div
                role="alert"
                className="mt-2 text-[12.5px] leading-[1.5] text-aside-review"
              >
                {errorMessage}
              </div>
            ) : null}

            <div className="mt-[18px] flex items-center gap-2.5 text-[13px] text-ink-60 max-md:text-sm">
              <input
                id="remember"
                type="checkbox"
                checked={remember}
                onChange={(e) => dispatch({ type: 'setRemember', value: e.target.checked })}
                className={[
                  'inline-grid h-4 w-4 cursor-pointer appearance-none place-items-center',
                  'border-[1.5px] border-hairline-strong bg-surface transition-colors duration-100',
                  'hover:border-ink-48',
                  'checked:border-action checked:bg-action',
                  "after:content-['']",
                  'checked:after:block checked:after:h-2 checked:after:w-1',
                  'checked:after:border-solid checked:after:border-white',

                  'checked:after:[border-width:0_1.6px_1.6px_0]',
                  'checked:after:[transform:rotate(45deg)_translateY(-1px)]',

                  'max-md:h-[18px] max-md:w-[18px]',
                  'max-md:checked:after:h-[9px] max-md:checked:after:w-[5px]',
                  'max-md:checked:after:[border-width:0_2px_2px_0]',
                ].join(' ')}
              />
              <label htmlFor="remember" className="cursor-pointer select-none">
                Keep me signed in on this device
              </label>
            </div>

            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="mt-[22px] flex w-full flex-nowrap items-center justify-center gap-2 whitespace-nowrap border-0 bg-action px-4 py-3.5 text-[15px] font-semibold tracking-[-0.005em] text-white transition-all duration-100 hover:bg-action-focus active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-ink-48 max-md:py-[15px] max-md:text-[15.5px]"
            >
              <span>{loginMutation.isPending ? 'Signing in…' : 'Sign in'}</span>
              <ArrowIcon />
            </button>
          </form>

          <div className="mt-[22px] flex flex-col items-start gap-2 border-t border-hairline pt-[18px] text-[13px] text-ink-60">
            <button
              type="button"
              className="border-b border-hairline pb-px font-medium text-ink-80 hover:border-action hover:text-action"
            >
              Trouble signing in?
            </button>
            <span>
              Need a hand?{' '}
              <a
                href="mailto:support@sift.app"
                className="border-b border-hairline pb-px font-medium text-ink-80 hover:border-action hover:text-action"
              >
                support@sift.app
              </a>
            </span>
          </div>
        </div>

        <div className="mt-auto flex items-center justify-between gap-3 font-mono text-[11.5px] tracking-[0.04em] text-ink-48 max-md:flex-col max-md:items-start max-md:gap-1.5 max-md:pt-6">
          <div className="flex items-center gap-3">
            <button type="button" className="text-ink-60 hover:text-ink">
              Privacy
            </button>
            <span className="text-hairline">·</span>
            <button type="button" className="text-ink-60 hover:text-ink">
              Terms
            </button>
            <span className="text-hairline">·</span>
            <button type="button" className="text-ink-60 hover:text-ink">
              Status
            </button>
          </div>
          <span className="md:ml-auto">v0.4 · build 2026.05.15</span>
        </div>
      </main>
    </div>
  )
}
