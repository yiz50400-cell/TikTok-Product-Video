import {measureText} from '@remotion/layout-utils';

// Wrap against the actual browser font; fail instead of clipping important copy.
export const fitLines = (text: string, width: number, maximum: number, minimum: number, maxLines: number) => {
  for (let fontSize = maximum; fontSize >= minimum; fontSize -= 2) {
    const lines: string[] = [];
    for (const paragraph of text.split('\n')) {
      let line = '';
      for (const char of Array.from(paragraph)) {
        const next = line + char;
        if (line && measureText({text: next, fontFamily: 'Arial', fontWeight: '700', fontSize}).width > width) {
          // Prefer word breaks; long words/CJK can split at character boundaries.
          const space = line.lastIndexOf(' ');
          if (space > 0) {
            lines.push(line.slice(0, space));
            line = line.slice(space + 1) + char;
          } else {
            lines.push(line);
            line = char;
          }
        } else line = next;
      }
      lines.push(line.trim());
    }
    if (lines.length <= maxLines) return {fontSize, text: lines.join('\n')};
  }
  throw new Error(`Text does not fit the safe area; shorten this copy: ${text}`);
};
