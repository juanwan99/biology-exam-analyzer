/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // momowan 墨绿主色
        primary: {
          50: '#f0f5f1',
          100: '#dce8df',
          200: '#b8d1bf',
          300: '#8ab596',
          400: '#5a9a6d',
          500: '#2d5a3d',
          600: '#1a2e1f',
          700: '#0f1c13',
          800: '#0a120c',
          900: '#050906',
          DEFAULT: '#1a2e1f',
          light: '#2d5a3d',
          dark: '#0f1c13',
        },
        // macaron 柔彩
        macaron: {
          mint: '#c8f0d4',
          'mint-light': '#e8f8ee',
          yellow: '#fef3c7',
          'yellow-light': '#fdf6e3',
          coral: '#fde8e8',
          'coral-light': '#fef0f0',
          purple: '#ede9fe',
          'purple-light': '#f3f0ff',
          blue: '#e0f2fe',
          'blue-light': '#ecf6ff',
        },
        // 语义色
        text: {
          DEFAULT: '#1a2e1f',
          secondary: '#5a6b5e',
          muted: '#8a9a8e',
        },
        border: {
          DEFAULT: '#e2e8e4',
          light: '#f0f4f1',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        'sm': '10px',
        'md': '14px',
        'lg': '20px',
        'xl': '24px',
        'pill': '50px',
      },
      boxShadow: {
        'sm': '0 1px 3px rgba(26, 46, 31, 0.04)',
        'md': '0 4px 12px rgba(26, 46, 31, 0.06)',
        'lg': '0 12px 32px rgba(26, 46, 31, 0.08)',
        'xl': '0 24px 48px rgba(26, 46, 31, 0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'scale-in': 'scaleIn 0.3s ease-out',
        'float': 'float 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      maxWidth: {
        'container': '1200px',
      },
    },
  },
  plugins: [],
}
