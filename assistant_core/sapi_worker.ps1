# Aster's small Windows-only local TTS bridge. It emits audio directly through
# the OS speech API and never creates an audio file.
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SetOutputToDefaultAudioDevice()
    $voices = @($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name })
    [Console]::Out.WriteLine((@{ event = 'ready'; voices = $voices } | ConvertTo-Json -Compress))
    $running = $true
    while ($running -and $null -ne ($line = [Console]::In.ReadLine())) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $command = $line | ConvertFrom-Json
            switch ([string]$command.type) {
                'speak' {
                    $text = [string]$command.text
                    if ([string]::IsNullOrWhiteSpace($text)) { continue }
                    $voiceName = [string]$command.voice
                    if ($voiceName) {
                        $voiceInfo = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -ceq $voiceName } | Select-Object -First 1
                        if ($null -eq $voiceInfo) {
                            [Console]::Out.WriteLine((@{ event = 'error'; message = 'That local voice is not installed.' } | ConvertTo-Json -Compress))
                            continue
                        }
                        $synth.SelectVoice($voiceName)
                    }
                    $rate = [Math]::Max(-30, [Math]::Min(30, [int]$command.rate * 3))
                    $pitch = [Math]::Max(-20, [Math]::Min(20, [int]$command.pitch * 2))
                    $culture = $synth.Voice.Culture.Name
                    $escaped = [System.Security.SecurityElement]::Escape($text)
                    $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='$culture'><prosody rate='${rate}%' pitch='${pitch}%'>$escaped</prosody></speak>"
                    $synth.SpeakSsmlAsync($ssml) | Out-Null
                    [Console]::Out.WriteLine((@{ event = 'started' } | ConvertTo-Json -Compress))
                }
                'stop' {
                    $synth.SpeakAsyncCancelAll()
                    [Console]::Out.WriteLine((@{ event = 'stopped' } | ConvertTo-Json -Compress))
                }
                'quit' {
                    $synth.SpeakAsyncCancelAll()
                    $running = $false
                    break
                }
            }
        }
        catch {
            [Console]::Out.WriteLine((@{ event = 'error'; message = 'Windows local speech could not process that request.' } | ConvertTo-Json -Compress))
        }
    }
}
catch {
    [Console]::Out.WriteLine((@{ event = 'error'; message = 'Windows local speech could not start. Check that a local speech voice is installed.' } | ConvertTo-Json -Compress))
    exit 1
}
finally {
    if ($null -ne $synth) { $synth.Dispose() }
}
