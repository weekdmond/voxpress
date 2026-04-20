import tokens from '../tokens.json';

const avatarGradients: string[] = tokens.avatarGradients;
const thumbGradients: string[] = tokens.thumbGradients;

export function avatarGradient(id: number): string {
  const n = avatarGradients.length;
  return avatarGradients[((id % n) + n) % n];
}

export function thumbGradient(seed: number): string {
  const n = thumbGradients.length;
  return thumbGradients[((seed % n) + n) % n];
}
