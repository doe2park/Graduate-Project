/** Static hosting paths are relative to the public page, including Pages project prefixes. */
export function deploymentPaths(documentURL) {
  const project = new URL('.', documentURL);
  const assets = new URL('bim-explorer-assets/', project);
  const resolve = (base, value) => {
    if (typeof value !== 'string' || !value || /^[\\/]|^[a-z][a-z\d+.-]*:/i.test(value)) {
      throw new Error('A project-relative resource path is required.');
    }
    const result = new URL(value, base);
    if (result.origin !== base.origin || !result.pathname.startsWith(base.pathname)) {
      throw new Error('Resource path is outside its configured directory.');
    }
    return result.href;
  };
  return {
    asset: value => resolve(assets, value),
    source: value => resolve(project, value)
  };
}
