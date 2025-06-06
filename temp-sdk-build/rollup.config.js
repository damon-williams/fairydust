import typescript from '@rollup/plugin-typescript';
import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import postcss from 'rollup-plugin-postcss';

export default [
  // Main SDK bundle
  {
    input: 'src/index.ts',
    output: [
      {
        file: 'dist/index.js',
        format: 'cjs',
        sourcemap: true
      },
      {
        file: 'dist/index.esm.js',
        format: 'esm',
        sourcemap: true
      },
      {
        file: 'dist/index.umd.js',
        format: 'umd',
        name: 'Fairydust',
        sourcemap: true,
        globals: {},
        exports: 'named'
      }
    ],
    plugins: [
      resolve({
        browser: true
      }),
      commonjs(),
      typescript({
        tsconfig: './tsconfig.json'
      }),
      postcss({
        extract: 'fairydust.css',
        minimize: true
      })
    ]
  },
  // Simple SDK bundle
  {
    input: 'src/simple.ts',
    output: {
      file: 'dist/simple.js',
      format: 'iife',
      sourcemap: true
    },
    plugins: [
      resolve({
        browser: true
      }),
      commonjs(),
      typescript({
        tsconfig: './tsconfig.json'
      })
    ]
  }
];