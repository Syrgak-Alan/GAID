import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:audioplayers/audioplayers.dart';

class AudioStreamingService {
  final String serverUrl;
  WebSocketChannel? _channel;
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _audioPlayer = AudioPlayer();
  StreamSubscription? _audioStream;
  bool _isConnected = false;

  // Audio queue for received audio chunks
  final List<Uint8List> _audioQueue = [];
  bool _isPlaying = false;

  // Callbacks
  Function(String)? onTextReceived;
  Function()? onTurnComplete;
  Function()? onInterrupted;

  AudioStreamingService({this.serverUrl = 'ws://localhost:8765'});

  Future<bool> connect() async {
    try {
      print('Connecting to WebSocket server at $serverUrl...');
      _channel = WebSocketChannel.connect(Uri.parse(serverUrl));

      _channel!.stream.listen((message) async {
        final data = jsonDecode(message);
        print('Received message type: ${data['type']}');

        switch (data['type']) {
          case 'ready':
            _isConnected = true;
            print('✅ Connected to server and ready');
            break;

          case 'audio':
          // Decode audio response
            final audioBytes = base64Decode(data['data']);
            print('🔊 Received audio chunk: ${audioBytes.length} bytes');
            _audioQueue.add(audioBytes);
            if (!_isPlaying) {
              _processAudioQueue();
            }
            break;

          case 'text':
          // Handle text transcription
            final text = data['data'];
            print('📝 Text received: $text');
            onTextReceived?.call(text);
            break;

          case 'turn_complete':
          // Model finished speaking
            print('✅ Turn complete');
            onTurnComplete?.call();
            break;

          case 'interrupted':
          // Response was interrupted
            print('🛑 Response interrupted');
            _audioQueue.clear();
            _isPlaying = false;
            await _audioPlayer.stop();
            onInterrupted?.call();
            break;

          case 'session_id':
          // Session ID received
            print('🔑 Session ID: ${data['data']}');
            break;

          case 'error':
            print('❌ Server error: ${data['data']}');
            break;

          default:
            print('Unknown message type: ${data['type']}');
        }
      }, onError: (error) {
        print('❌ WebSocket error: $error');
        _isConnected = false;
      }, onDone: () {
        print('WebSocket connection closed');
        _isConnected = false;
      });

      // Wait for ready signal
      await Future.delayed(const Duration(seconds: 2));
      return _isConnected;
    } catch (e) {
      print('❌ Connection error: $e');
      return false;
    }
  }

  Future<void> startStreaming() async {
    print('Starting audio streaming...');

    if (!_isConnected) {
      print('Not connected, attempting to connect...');
      final connected = await connect();
      if (!connected) {
        print('❌ Failed to connect to server');
        return;
      }
    }

    // Check microphone permission
    if (!await _recorder.hasPermission()) {
      print('❌ Microphone permission not granted');
      return;
    }

    // Configure audio recording for 16kHz, 16-bit PCM
    const config = RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
      autoGain: true,
      echoCancel: true,
      noiseSuppress: true,
    );

    print('📤 Starting audio recording with config: 16kHz, 16-bit PCM, mono');

    // Start recording with stream
    try {
      final stream = await _recorder.startStream(config);

      _audioStream = stream.listen((data) {
        // Convert to base64 and send
        final base64Audio = base64Encode(data);
        _channel?.sink.add(jsonEncode({
          'type': 'audio',
          'data': base64Audio,
        }));
        print('📤 Sent audio chunk: ${data.length} bytes');
      }, onError: (error) {
        print('❌ Recording error: $error');
      });

      print('✅ Audio streaming started');
    } catch (e) {
      print('❌ Failed to start recording: $e');
    }
  }

  Future<void> stopStreaming() async {
    print('Stopping audio streaming...');

    await _audioStream?.cancel();
    await _recorder.stop();

    // Send end signal
    if (_channel != null && _isConnected) {
      _channel!.sink.add(jsonEncode({'type': 'end'}));
      print('📤 Sent end signal to server');
    }

    print('✅ Audio streaming stopped');
  }

  Future<void> _processAudioQueue() async {
    if (_isPlaying || _audioQueue.isEmpty) {
      return;
    }

    _isPlaying = true;

    while (_audioQueue.isNotEmpty) {
      final pcmData = _audioQueue.removeAt(0);

      // Create WAV from PCM (server sends 24kHz 16-bit PCM)
      final wavData = _createWavFromPcm(pcmData, 24000);

      try {
        // Play using BytesSource
        await _audioPlayer.play(
          BytesSource(wavData),
          mode: PlayerMode.lowLatency,
        );
        print('🔊 Playing audio chunk: ${pcmData.length} bytes');

        // Wait for completion (estimate based on data size)
        // 24kHz, 16-bit mono = 48000 bytes per second
        final durationMs = (pcmData.length * 1000) ~/ 48000;
        await Future.delayed(Duration(milliseconds: durationMs));

      } catch (e) {
        print('❌ Error playing audio: $e');
      }
    }

    _isPlaying = false;
  }

  Uint8List _createWavFromPcm(Uint8List pcmData, int sampleRate) {
    final numChannels = 1;
    final bitsPerSample = 16;
    final byteRate = sampleRate * numChannels * bitsPerSample ~/ 8;
    final blockAlign = numChannels * bitsPerSample ~/ 8;
    final dataSize = pcmData.length;
    final fileSize = dataSize + 36;

    final wavHeader = BytesBuilder();

    // RIFF header
    wavHeader.add(utf8.encode('RIFF'));
    wavHeader.add(_int32ToBytes(fileSize));
    wavHeader.add(utf8.encode('WAVE'));

    // fmt chunk
    wavHeader.add(utf8.encode('fmt '));
    wavHeader.add(_int32ToBytes(16)); // fmt chunk size
    wavHeader.add(_int16ToBytes(1)); // audio format (PCM)
    wavHeader.add(_int16ToBytes(numChannels));
    wavHeader.add(_int32ToBytes(sampleRate));
    wavHeader.add(_int32ToBytes(byteRate));
    wavHeader.add(_int16ToBytes(blockAlign));
    wavHeader.add(_int16ToBytes(bitsPerSample));

    // data chunk
    wavHeader.add(utf8.encode('data'));
    wavHeader.add(_int32ToBytes(dataSize));
    wavHeader.add(pcmData);

    return wavHeader.toBytes();
  }

  Uint8List _int16ToBytes(int value) {
    final bytes = ByteData(2);
    bytes.setInt16(0, value, Endian.little);
    return bytes.buffer.asUint8List();
  }

  Uint8List _int32ToBytes(int value) {
    final bytes = ByteData(4);
    bytes.setInt32(0, value, Endian.little);
    return bytes.buffer.asUint8List();
  }

  bool get isConnected => _isConnected;
  bool get isRecording => _audioStream != null;

  void dispose() {
    print('Disposing AudioStreamingService...');
    _audioStream?.cancel();
    _recorder.dispose();
    _audioPlayer.dispose();
    _channel?.sink.close();
    print('✅ AudioStreamingService disposed');
  }
}