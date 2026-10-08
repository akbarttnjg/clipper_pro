import {defineConfig} from 'vite';
import motionCanvas from '@motion-canvas/vite-plugin';
export default defineConfig({plugins:[motionCanvas({project:'./src/project.ts'})],server:{host:'127.0.0.1',port:0,strictPort:false},logLevel:'error'});
