/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,jsx}",
    "./components/**/*.{js,jsx}",
    "./app/**/*.{js,jsx}",
    "./src/**/*.{js,jsx}"
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px"
      }
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))"
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))"
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))"
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))"
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))"
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))"
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))"
        },
        // violet-600 is #7C3AED — the brand colour, hardcoded as a utility in
        // ~100 places that predate the `primary` token. Pointing that one shade
        // at a variable makes every `bg-violet-600`, `hover:bg-violet-600` and
        // `bg-violet-600/90` follow the theme: #427CF5 in light, #7C3AED in
        // dark. `<alpha-value>` keeps the opacity modifiers working.
        violet: {
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "hsl(var(--brand-600) / <alpha-value>)",
          700: "#6d28d9"
        },
        // The agent dashboards were built for a dark page, so surfaces and
        // text are written as white-with-opacity: `text-white`, `text-white/60`,
        // `bg-white/5`, `border-white/10` — about 4,000 of them. On a light
        // page every one of those is invisible. Rather than rewrite each call
        // site, `white` points at a token that is near-black in light mode and
        // real white in dark mode, so they all invert together.
        // Use `pure-white` where the colour must stay white regardless — text
        // sitting on a coloured or gradient button, for example.
        white: "hsl(var(--surface-invert) / <alpha-value>)",
        "pure-white": "#ffffff",
        // Same idea for `black`: `bg-black/20` is an inset panel on a dark
        // page, so it has to lighten rather than stay charcoal. Modal scrims
        // keep real black via `pure-black`.
        black: "hsl(var(--surface-base) / <alpha-value>)",
        "pure-black": "#000000"
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)"
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" }
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" }
        },
        "pulse-slow": {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 12px 0 rgba(162,89,255,0.25)" },
          "50%": { opacity: "0.75", boxShadow: "0 0 18px 2px rgba(162,89,255,0.45)" }
        },
        "blink": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.15" }
        },
        "nudge-x": {
          "0%, 100%": { transform: "translateX(0)" },
          "50%": { transform: "translateX(4px)" }
        }
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "pulse-slow": "pulse-slow 2.4s ease-in-out infinite",
        "blink": "blink 0.9s step-start infinite",
        "nudge-x": "nudge-x 0.8s ease-in-out infinite"
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        heading: ["Cal Sans", "sans-serif"]
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
}