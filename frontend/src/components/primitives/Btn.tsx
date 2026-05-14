import type { ComponentType, MouseEvent, ReactNode } from 'react'

type Variant = 'primary' | 'ghost' | 'danger' | undefined
type Size = 'sm' | undefined

type Props = {
  children?: ReactNode
  variant?: Variant
  size?: Size
  icon?: ComponentType
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void
  title?: string
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}

export function Btn({
  children,
  variant,
  size,
  icon: IconComp,
  onClick,
  title,
  disabled,
  type = 'button',
}: Props) {
  return (
    <button
      type={type}
      className="btn"
      data-variant={variant}
      data-size={size}
      onClick={onClick}
      title={title}
      disabled={disabled}
    >
      {IconComp && <IconComp />}
      {children && <span>{children}</span>}
    </button>
  )
}
