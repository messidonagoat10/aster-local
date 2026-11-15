"use strict";

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.sampleRemainder = 0;
    this.frame = [];
    this.speechSeen = false;
    this.quietFrames = 0;
    this.frameSamples = 320; // 20 ms at 16 kHz
  }

  process(inputs, outputs) {
    const sink = outputs[0] && outputs[0][0];
    if (sink) sink.fill(0);
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    const ratio = sampleRate / 16000;
    const output = [];
    for (let index = 0; index < channel.length; index += 1) {
      this.sampleRemainder += 16000;
      if (this.sampleRemainder >= sampleRate) {
        this.sampleRemainder -= sampleRate;
        const sample = Math.max(-1, Math.min(1, channel[index]));
        output.push(sample < 0 ? sample * 32768 : sample * 32767);
      }
    }

    for (const sample of output) {
      this.frame.push(sample);
      if (this.frame.length < this.frameSamples) continue;
      let energy = 0;
      const pcm = new Int16Array(this.frame.length);
      for (let index = 0; index < this.frame.length; index += 1) {
        pcm[index] = this.frame[index];
        const normalized = this.frame[index] / 32768;
        energy += normalized * normalized;
      }
      const rms = Math.sqrt(energy / this.frame.length);
      this.port.postMessage({ type: "pcm", buffer: pcm.buffer }, [pcm.buffer]);
      if (rms >= 0.012) {
        this.speechSeen = true;
        this.quietFrames = 0;
      } else if (this.speechSeen) {
        this.quietFrames += 1;
        if (this.quietFrames >= 75) {
          this.port.postMessage({ type: "silence-end" });
          this.speechSeen = false;
          this.quietFrames = 0;
        }
      }
      this.frame = [];
    }
    return true;
  }
}

registerProcessor("aster-pcm-capture", PcmCaptureProcessor);
