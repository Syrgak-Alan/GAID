import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:permission_handler/permission_handler.dart';

import 'audio_streaming_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
      ),
      home: const MyHomePage(title: 'Flutter Demo Home Page'),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});

  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  CameraController? _controller;
  bool _isInitialized = false;
  bool _isRecording = false;  // Add this
  late AudioStreamingService _audioService;

  @override
  void initState() {
    super.initState();
    _audioService = AudioStreamingService();  // Initialize service
    _initPermissions();
    _initCamera();
  }

  _initPermissions() async {
    await Permission.microphone.request();
  }

  _initCamera() async {
    try {
      // Request camera permission
      final status = await Permission.camera.request();
      if (status.isGranted) {
        final cameras = await availableCameras();
        if (cameras.isNotEmpty) {
          _controller = CameraController(cameras[0], ResolutionPreset.high);
          await _controller!.initialize();
          setState(() {
            _isInitialized = true;
          });
        }
      } else {
        print('Camera permission denied');
      }
    } catch (e) {
      print('Error initializing camera: $e');
    }
  }

  void _toggleRecording() async {
    setState(() {
      _isRecording = !_isRecording;
    });

    if (_isRecording) {
      await _audioService.startStreaming();
    } else {
      await _audioService.stopStreaming();
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    _audioService.dispose();  // Clean up
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // Camera preview fills entire screen
          if (_isInitialized && _controller != null)
            Positioned.fill(
              child: CameraPreview(_controller!),
            )
          else
            const Positioned.fill(
              child: Center(
                child: CircularProgressIndicator(),
              ),
            ),
          // Microphone button at bottom center
          Positioned(
            bottom: 50,
            left: MediaQuery.of(context).size.width / 2 - 35,
            child: Container(
              width: 70,
              height: 70,
              decoration: BoxDecoration(
                color: _isRecording ? Colors.red : Colors.green,
                shape: BoxShape.circle,
              ),
              child: IconButton(
                onPressed: _toggleRecording,
                icon: const Icon(
                  Icons.mic,
                  color: Colors.white,
                  size: 30,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}