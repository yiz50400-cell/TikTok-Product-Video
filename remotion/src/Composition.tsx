import {fitLines} from './text-layout';
import {Audio, Video} from '@remotion/media';
import type {Caption} from '@remotion/captions';
import {AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type ProductProps = {
  video: string;
  durationInFrames: number;
  fps: number;
  audioMode: 'silent' | 'narration';
  title: string;
  cta: string;
  accentColor: string;
  captions: Caption[];
  cards: {text: string; start: number; end: number}[];
};

const Enter: React.FC<React.PropsWithChildren> = ({children}) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{
    opacity: interpolate(frame, [0, 6], [0, 1], {extrapolateRight: 'clamp'}),
  }}>{children}</AbsoluteFill>;
};

const Captions: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cue = captions.find((c) => c.startMs <= frame / fps * 1000 && c.endMs > frame / fps * 1000);
  if (!cue) return null;
  const fitted = fitLines(cue.text, 780, 50, 40, 4);
  return <div style={{position: 'absolute', left: 80, right: 160, bottom: 400,
    textAlign: 'center', fontSize: fitted.fontSize, fontWeight: 700, lineHeight: 1.22,
    color: '#fff', whiteSpace: 'pre',
    textShadow: '0 3px 8px #000', background: 'rgba(0,0,0,0.68)',
    padding: '20px 26px', borderRadius: 16}}>{fitted.text}</div>;
};

export const ProductPackaging: React.FC<ProductProps> = (props) => {
  const {fps, durationInFrames} = useVideoConfig();
  const title = fitLines(props.title, 768, 64, 44, 4);
  const cta = fitLines(props.cta, 784, 46, 32, 2);
  const cards = props.cards.map((c) => ({...c, fitted: fitLines(c.text, 780, 48, 36, 3)}));
  return <AbsoluteFill style={{backgroundColor: '#080b10', fontFamily: 'Arial, sans-serif'}}>
    {/* Timing and shot decisions remain in the clean ChatCut export. */}
    <Video src={staticFile(props.video)} muted style={{width: '100%', height: '100%'}} objectFit="contain" />
    {props.audioMode === 'narration' ? <Audio src={staticFile(props.video)} /> : null}
    {props.title ? <Sequence durationInFrames={Math.min(3 * fps, durationInFrames)}>
      <Enter><div style={{position: 'absolute', top: 190, left: 80, right: 160,
        fontSize: title.fontSize, fontWeight: 700, lineHeight: 1.15, color: '#fff',
        whiteSpace: 'pre', borderLeft: `8px solid ${props.accentColor}`,
        background: 'rgba(0,0,0,0.72)', padding: '24px 28px'}}>{title.text}</div></Enter>
    </Sequence> : null}
    {cards.map((card, i) => <Sequence key={i} from={Math.round(card.start * fps)}
      durationInFrames={Math.round(card.end * fps) - Math.round(card.start * fps)}>
      <Enter><div style={{position: 'absolute', top: 680, left: 80, right: 160,
        background: props.accentColor, color: '#101820', fontSize: card.fitted.fontSize,
        lineHeight: 1.2, fontWeight: 700, borderRadius: 22, padding: '24px 30px',
        whiteSpace: 'pre'}}>{card.fitted.text}</div></Enter>
    </Sequence>)}
    <Captions captions={props.captions} />
    {props.cta ? <Sequence from={Math.max(0, durationInFrames - 3 * fps)}>
      <Enter><div style={{position: 'absolute', bottom: 210, left: 80, right: 160,
        padding: '22px 28px', background: props.accentColor, color: '#101820',
        borderRadius: 18, textAlign: 'center', fontSize: cta.fontSize, lineHeight: 1.15,
        fontWeight: 700, whiteSpace: 'pre'}}>{cta.text}</div></Enter>
    </Sequence> : null}
  </AbsoluteFill>;
};
