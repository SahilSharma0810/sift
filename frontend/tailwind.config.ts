import type { Config } from 'tailwindcss'
import tailwindAnimate from 'tailwindcss-animate'

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f5f5f7',
        surface: {
          DEFAULT: '#ffffff',
          recess: '#f5f5f7',
          pearl: '#fafafc',
        },
        tile: '#1d1d1f',
        ink: {
          DEFAULT: '#1d1d1f',
          80: '#333333',
          60: '#6e6e73',
          48: '#86868b',
        },
        light: {
          DEFAULT: '#ffffff',
          muted: '#a1a1a6',
          subtle: '#6e6e73',
        },
        hairline: {
          DEFAULT: '#e0e0e0',
          soft: '#ececec',
          strong: '#c0c0c4',
          dark: 'rgb(255 255 255 / 0.10)',
        },
        action: {
          DEFAULT: '#0066cc',
          focus: '#0071e3',
          light: '#2997ff',
          soft: '#e9f0f9',
        },
        triage: {
          confident: {
            DEFAULT: '#0a7c46',
            tint: '#e8f3ec',
            ring: '#c4e0cd',
          },
          'needs-review': {
            DEFAULT: '#b25b00',
            tint: '#fbf0e3',
            ring: '#ebd0a8',
          },
          duplicate: {
            DEFAULT: '#1e5fc2',
            tint: '#e9f0fb',
            ring: '#c4d4ee',
          },
          unprocessable: {
            DEFAULT: '#6e6e73',
            tint: '#f0f0f2',
          },
        },
        aside: {
          confident: {
            DEFAULT: '#6fd393',
            ring: '#1f4d2e',
            tint: '#11281a',
          },
          review: {
            DEFAULT: '#ffb95f',
            ring: '#4e3a16',
            tint: '#2a1e09',
          },
          duplicate: {
            DEFAULT: '#8fb7ee',
            ring: '#1d3a66',
            tint: '#0d1f3a',
          },
        },
        soc2: '#34c759',
        'anomaly-amount-fg':       'oklch(0.45 0.13 25)',
        'anomaly-amount-bg':       'oklch(0.96 0.04 25)',
        'anomaly-amount-ring':     'oklch(0.88 0.07 25)',
        'anomaly-frequency-fg':    'oklch(0.42 0.13 290)',
        'anomaly-frequency-bg':    'oklch(0.96 0.04 290)',
        'anomaly-frequency-ring':  'oklch(0.88 0.07 290)',
        'anomaly-severity-high':   'oklch(0.55 0.18 25)',
      },

      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
        mono: ['"Geist Mono"', '"SF Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },

      backgroundImage: {
        'aside-glow':
          'radial-gradient(circle, rgb(41 151 255 / 0.16) 0%, transparent 65%)',
      },

      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
      },

      animation: {
        'fade-up': 'fade-up 220ms ease both',
      },
    },
  },
  plugins: [tailwindAnimate],
} satisfies Config
