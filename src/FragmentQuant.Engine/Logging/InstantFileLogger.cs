using System;
using System.IO;
using System.Text;

namespace FragmentQuant.Engine.Logging
{
    public sealed class InstantFileLogger : IDisposable
    {
        private readonly string _componentName;
        private readonly StreamWriter? _fileWriter;
        private readonly object _syncLock;
        private readonly bool _subordinateMode;
        private bool _isDisposed;

        public InstantFileLogger(string componentName, string rootDirectoryPath, bool subordinateMode = false)
        {
            _componentName = componentName;
            _syncLock = new object();
            _subordinateMode = subordinateMode;
            _isDisposed = false;

            if (!_subordinateMode)
            {
                string logFilePath = Path.Combine(rootDirectoryPath, "logs.txt");
                FileStream fileStream = new FileStream(
                    logFilePath,
                    FileMode.Create,
                    FileAccess.Write,
                    FileShare.ReadWrite
                );

                _fileWriter = new StreamWriter(fileStream, new UTF8Encoding(false))
                {
                    AutoFlush = true
                };
            }
        }

        public void LogInfo(string message)
        {
            WriteRecord("INFO", message);
        }

        public void LogWarning(string message)
        {
            WriteRecord("WARNING", message);
        }

        public void LogError(string message, Exception? exception = null)
        {
            string fullMessage = exception != null
                ? $"{message} | Exception: {exception.GetType().Name}: {exception.Message}"
                : message;
            WriteRecord("ERROR", fullMessage);
        }

        private void WriteRecord(string level, string message)
        {
            lock (_syncLock)
            {
                if (_isDisposed)
                {
                    return;
                }

                if (_subordinateMode)
                {
                    Console.WriteLine(message);
                    return;
                }

                string timestamp = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss.fff");
                string formattedLine = $"{timestamp} | {level,-8} | [{_componentName}] {message}";

                Console.WriteLine(formattedLine);
                if (_fileWriter != null)
                {
                    _fileWriter.WriteLine(formattedLine);
                    _fileWriter.Flush();
                }
            }
        }

        public void Dispose()
        {
            lock (_syncLock)
            {
                if (!_isDisposed)
                {
                    if (_fileWriter != null)
                    {
                        _fileWriter.Flush();
                        _fileWriter.Dispose();
                    }
                    _isDisposed = true;
                }
            }
        }
    }
}
