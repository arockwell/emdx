import * as esbuild from 'esbuild';

const isProduction = process.argv.includes('--production');
const isWatch = process.argv.includes('--watch');
const isWebviewOnly = process.argv.includes('--webview');

// Extension host config (Node.js target)
const extensionConfig = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'dist/extension.js',
  external: ['vscode'], // vscode is provided by the runtime
  format: 'cjs',
  platform: 'node',
  target: 'node18',
  sourcemap: !isProduction,
  minify: isProduction,
};

// Webview configs (browser target, one per panel)
const webviewConfig = {
  entryPoints: [
    'webview/src/activity/index.tsx',
    'webview/src/tasks/index.tsx',
    'webview/src/qa/index.tsx',
  ],
  bundle: true,
  outdir: 'dist/webview',
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  sourcemap: !isProduction,
  minify: isProduction,
  loader: {
    '.css': 'css',
  },
};

async function build() {
  if (isWatch) {
    // Use esbuild context API for watch mode
    const contexts = [];

    if (!isWebviewOnly) {
      const extCtx = await esbuild.context(extensionConfig);
      contexts.push(extCtx);
      console.log('[watch] Extension host build started');
    }

    const webviewCtx = await esbuild.context(webviewConfig);
    contexts.push(webviewCtx);
    console.log('[watch] Webview build started');

    // Start watching all contexts
    await Promise.all(contexts.map((ctx) => ctx.watch()));
    console.log('[watch] Watching for changes...');

    // Keep process alive; clean up on SIGINT/SIGTERM
    const cleanup = async () => {
      console.log('\n[watch] Stopping...');
      await Promise.all(contexts.map((ctx) => ctx.dispose()));
      process.exit(0);
    };
    process.on('SIGINT', cleanup);
    process.on('SIGTERM', cleanup);
  } else {
    // One-shot build
    const builds = [];

    if (!isWebviewOnly) {
      builds.push(
        esbuild.build(extensionConfig).then(() => {
          console.log('Extension host bundle built');
        })
      );
    }

    builds.push(
      esbuild.build(webviewConfig).then(() => {
        console.log('Webview bundles built');
      })
    );

    await Promise.all(builds);
    console.log(isProduction ? 'Production build complete' : 'Development build complete');
  }
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
