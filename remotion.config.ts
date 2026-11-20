import fs from 'fs';
import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);

// Булуттагы сервер үчүн гана: даяр браузерди колдонобуз.
// Сиздин компьютериңизде бул файл жок, Remotion өзү браузерди жүктөйт.
const cloudBrowser = '/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell';
if (fs.existsSync(cloudBrowser)) {
  Config.setBrowserExecutable(cloudBrowser);
}
