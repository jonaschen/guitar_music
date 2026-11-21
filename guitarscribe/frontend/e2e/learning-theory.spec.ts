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
