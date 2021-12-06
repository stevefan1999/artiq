use core::str::Utf8Error;
use embedded_websocket as ws;
use embedded_websocket::{
    framer::{Framer, FramerError, Stream as FramerStream},
    WebSocketContext, WebSocketSendMessageType, WebSocketServer,
};
use io::Error as LibIoError;
use sched::{Error as SchedError, Io, TcpListener, TcpStream};

type Result<T> = core::result::Result<T, WebServerError>;

#[derive(Debug)]
pub enum WebServerError {
    Io(SchedError),
    Framer(FramerError<SchedError>),
    Http(httparse::Error),
    WebSocket(ws::Error),
    Utf8Error(core::str::Utf8Error),
}

impl From<SchedError> for WebServerError {
    fn from(err: SchedError) -> WebServerError {
        WebServerError::Io(err)
    }
}

impl From<FramerError<SchedError>> for WebServerError {
    fn from(err: FramerError<SchedError>) -> WebServerError {
        WebServerError::Framer(err)
    }
}

impl From<httparse::Error> for WebServerError {
    fn from(err: httparse::Error) -> WebServerError {
        WebServerError::Http(err)
    }
}

impl From<ws::Error> for WebServerError {
    fn from(err: ws::Error) -> WebServerError {
        WebServerError::WebSocket(err)
    }
}

impl From<Utf8Error> for WebServerError {
    fn from(err: Utf8Error) -> WebServerError {
        WebServerError::Utf8Error(err)
    }
}

pub fn thread(io: Io) {
    let listener = TcpListener::new(&io, 4096);
    listener.listen(1337).expect("http_fun: cannot listen");
    info!("http server activated");

    loop {
        let stream = listener
            .accept()
            .expect("mgmt: cannot accept")
            .into_handle();
        io.spawn(4096, move |io| {
            let mut stream = TcpStream::from_handle(&io, stream);
            match handle_client(&mut stream) {
                Ok(()) => info!("connection closed"),
                Err(WebServerError::Io(SchedError::Interrupted)) => error!("unexpected end"),
                Err(_err) => error!("aborted"),
            }
        });
    }
}

fn handle_client(stream: &mut TcpStream) -> Result<()> {
    info!("client connected {}", stream.remote_endpoint());
    let mut read_buf = [0u8; 4096];
    let mut read_cursor = 0;

    if let Some(websocket_context) = read_header(stream.into(), &mut read_buf, &mut read_cursor)? {
        info!("Websocket connection requested");
        // this is a websocket upgrade HTTP request
        let mut write_buf = [0u8; 4096];
        let mut frame_buf = [0u8; 4096];
        let mut websocket = WebSocketServer::new_server();
        let mut framer = Framer::new(
            &mut read_buf,
            &mut read_cursor,
            &mut write_buf,
            &mut websocket,
        );

        // complete the opening handshake with the client
        framer.accept(stream.into(), &websocket_context)?;
        info!("Websocket connection opened");

        // read websocket frames
        while let Some(text) = framer.read_text(stream.into(), &mut frame_buf)? {
            info!("Received: {}", text);

            // send the text back to the client
            framer.write(
                stream.into(),
                WebSocketSendMessageType::Text,
                true,
                text.as_bytes(),
            )?
        }

        info!("Closing websocket connection");
    }
    Ok(())
}

fn read_header(
    stream: &mut TcpStream,
    read_buf: &mut [u8],
    read_cursor: &mut usize,
) -> Result<Option<WebSocketContext>> {
    loop {
        let mut headers = [httparse::EMPTY_HEADER; 64];
        let mut request = httparse::Request::new(&mut headers);

        let received_size = stream.read(&mut read_buf[*read_cursor..])?;
        // info!("http read {} {}", stream.remote_endpoint(), received_size);

        match request.parse(&read_buf[..*read_cursor + received_size])? {
            // keep reading while the HTTP header is incomplete
            httparse::Status::Partial => {
                // info!("http parsing partial {}", stream.remote_endpoint());
                *read_cursor += received_size;
            }
            httparse::Status::Complete(len) => {
                info!("http parsing complete {}", stream.remote_endpoint());
                // if we read exactly the right amount of bytes for the HTTP header then read_cursor would be 0
                *read_cursor += received_size - len;
                let headers = request.headers.into_iter().map(|f| (f.name, f.value));
                match ws::read_http_header(headers)? {
                    Some(websocket_context) => match request.path {
                        Some("/chat") => return Ok(Some(websocket_context)),
                        _ => {
                            return_404_not_found(stream, request.path)?;
                        }
                    },
                    None => {
                        handle_non_websocket_http_request(stream, request.path)?;
                    }
                }

                return Ok(None);
            }
        }
    }
}

fn handle_non_websocket_http_request(stream: &mut TcpStream, path: Option<&str>) -> Result<()> {
    info!("Received file request: {:?}", path);

    match path {
        Some("/") => FramerStream::write_all(stream.into(), &ROOT_HTML.as_bytes())?,
        unknown_path => {
            return_404_not_found(stream, unknown_path)?;
        }
    };

    Ok(())
}

fn return_404_not_found(stream: &mut TcpStream, unknown_path: Option<&str>) -> Result<()> {
    error!("Unknown path: {:?}", unknown_path);
    let html = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    FramerStream::write_all(stream.into(), &html.as_bytes())?;
    Ok(())
}

impl FramerStream<SchedError> for TcpStream<'_> {
    fn read(&mut self, buf: &mut [u8]) -> core::result::Result<usize, SchedError> {
        io::Read::read(self, buf)
    }

    fn write_all(&mut self, buf: &[u8]) -> core::result::Result<(), SchedError> {
        match io::Write::write_all(self, buf) {
            Ok(ok) => Ok(ok),
            Err(LibIoError::UnexpectedEnd) => Err(SchedError::Interrupted),
            Err(LibIoError::Other(err)) => Err(err),
        }
    }
}

const ROOT_HTML : &'static str = "HTTP/1.1 200 OK\r
Content-Type: text/html; charset=UTF-8\r
Content-Length: 2585\r
Connection: keep-alive\r
\r
<!doctype html>
<html>
<head>
    <meta content='text/html;charset=utf-8' http-equiv='Content-Type' />
    <meta content='utf-8' http-equiv='encoding' />
    <meta name='viewport' content='width=device-width, initial-scale=0.5, maximum-scale=0.5, user-scalable=0' />
    <meta name='apple-mobile-web-app-capable' content='yes' />
    <meta name='apple-mobile-web-app-status-bar-style' content='black' />
    <title>Web Socket Demo</title>
    <style type='text/css'>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font: 13px Helvetica, Arial; }
        form { background: #000; padding: 3px; position: fixed; bottom: 0; width: 100%; }
        form input { border: 0; padding: 10px; width: 90%; margin-right: .5%; }
        form button { width: 9%; background: rgb(130, 200, 255); border: none; padding: 10px; }
        #messages { list-style-type: none; margin: 0; padding: 0; }
        #messages li { padding: 5px 10px; }
        #messages li:nth-child(odd) { background: #eee; }
    </style>
</head>
<body>
    <ul id='messages'></ul>
    <form action=''>
    <input id='txtBox' autocomplete='off' /><button>Send</button>
    </form>
    <script type='text/javascript' src='http://code.jquery.com/jquery-1.11.1.js' ></script>
    <script type='text/javascript'>
        var CONNECTION;
        window.onload = function () {
            // open the connection to the Web Socket server
            // CONNECTION = new WebSocket('ws://localhost:1337/chat');
			CONNECTION = new WebSocket('ws://' + location.host + '/chat');

            // When the connection is open
            CONNECTION.onopen = function () {
                $('#messages').append($('<li>').text('Connection opened'));
            };

            // when the connection is closed by the server
            CONNECTION.onclose = function () {
                $('#messages').append($('<li>').text('Connection closed'));
            };

            // Log errors
            CONNECTION.onerror = function (e) {
                console.log('An error occured');
            };

            // Log messages from the server
            CONNECTION.onmessage = function (e) {
                $('#messages').append($('<li>').text(e.data));
            };
        };

		$(window).on('beforeunload', function(){
			CONNECTION.close();
		});

        // when we press the Send button, send the text to the server
        $('form').submit(function(){
            CONNECTION.send($('#txtBox').val());
            $('#txtBox').val('');
            return false;
        });
    </script>
</body>
</html>";
