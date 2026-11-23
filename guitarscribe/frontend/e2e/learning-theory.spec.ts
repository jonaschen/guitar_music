import {test,expect} from '@playwright/test';
import {chordTones,compareChordTones,relativeKey} from '../src/chordTheory';
test('theory spells thirds and extensions by degree, including enharmonic roots',()=>{
 expect(chordTones('C#')?.tones.map(t=>t.name)).toEqual(['C#','E#','G#']);
 expect(chordTones('Gm7')?.tones.map(t=>t.name)).toEqual(['G','Bb','D','F']);
 expect(chordTones('Bdim7')?.tones.map(t=>t.name)).toEqual(['B','D','F','Ab']);
 expect(chordTones('Caug')?.tones.map(t=>t.name)).toEqual(['C','E','G#']);
 expect(chordTones('C#aug')?.tones.map(t=>t.name)).toEqual(['C#','E#','G##']);
 expect(chordTones('G5')?.tones.map(t=>t.degree)).toEqual(['1','5']);
 expect(chordTones('Gsus4')?.tones.map(t=>t.name)).toEqual(['G','C','D']);
});
test('comparison separates bass, root, shared tones and differences without claiming audio evidence',()=>{
 const slash=chordTones('C/E')!;expect(slash.root).toBe('C');expect(slash.bass).toBe('E');
 const comparison=compareChordTones('G','Gm')!;expect(comparison.onlyA.map(t=>t.name)).toEqual(['B']);expect(comparison.onlyB.map(t=>t.name)).toEqual(['Bb']);
 expect(compareChordTones('C6','Am7')?.samePitchClasses).toBe(true);
 expect(chordTones('E7')?.tones.map(t=>t.name)).toEqual(['E','G#','B','D']);
 expect(chordTones('N.C.')).toBeNull();expect(chordTones('Ccomplex')).toBeNull();expect(chordTones('')).toBeNull();
});
test('relative major and minor are comparison hypotheses, preserving degree spelling',()=>{
 expect(relativeKey('C','major')).toEqual({tonic:'A',mode:'minor'});
 expect(relativeKey('C#','major')).toEqual({tonic:'A#',mode:'minor'});
 expect(relativeKey('A','minor')).toEqual({tonic:'C',mode:'major'});
 expect(relativeKey('A','other')).toBeNull();
});

test('relative chord labels preserve tonic hypotheses, quality, spelling and independent bass',async()=>{
 const {relativeChord}=await import('../src/chordTheory');
 expect(relativeChord('Am','C','major')).toMatchObject({roman:'vi',number:'6m'});
 expect(relativeChord('E7','A','minor')).toMatchObject({roman:'V7',number:'5(7)'});
 expect(relativeChord('C','A','minor')).toMatchObject({roman:'♭III',number:'♭3'});
 expect(relativeChord('F','A','minor')).toMatchObject({roman:'♭VI',number:'♭6'});
 expect(relativeChord('G#dim','A','minor')?.roman).toBe('vii°');
 expect(relativeChord('Bb','C','major')?.roman).toBe('♭VII');
 expect(relativeChord('D#m','C','major')?.roman).toBe('♯ii');
 expect(relativeChord('E#','C#','major')?.roman).toBe('III');
 expect(relativeChord('C/E','C','major')).toMatchObject({roman:'I',bassName:'E',bassDegree:'3'});
 expect(relativeChord('Bdim7','C','major')?.roman).toBe('vii°7');
 expect(relativeChord('Bm7b5','C','major')?.roman).toBe('viiø7');
 expect(relativeChord('Gsus4','C','major')?.roman).toBe('Vsus4');
 expect(relativeChord('G5','C','major')?.roman).toBe('V(no3)');
 expect(relativeChord('Cmaj7','C','major')?.number).toBe('1(maj7)');
 expect(relativeChord('C6','C','major')?.roman).toBe('I(add6)');
 expect(relativeChord('C/E','C','major')?.roman).toBe('I');
 for(const args of [['G',null,'major'],['G','C','unknown'],['G','C','other'],['Ccomplex','C','major'],['N.C.','C','major']] as const){expect(relativeChord(...args)).toBeNull();}
});
