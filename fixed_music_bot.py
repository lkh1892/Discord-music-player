import os
import asyncio
import datetime
import json
import discord
from discord import File
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands  # 슬래시 명령어를 위한 임포트
from dotenv import load_dotenv
import yt_dlp
import ffmpeg

# yt-dlp 옵션 설정
yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # IPv6 주소에서 바인딩 문제 방지
    # 캐싱 추가 - 자주 검색하는 곡을 빠르게 로드할 수 있음
    'cachedir': './ytdl_cache',  # 캐시 디렉토리
    'no_cache_dir': False,       # 캐시 사용 활성화
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# .env 파일에서 환경 변수 로드
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# FFMPEG 경로 설정 (실제 경로로 변경 필요)
FFMPEG_PATH = r"C:/ffmpeg/bin/ffmpeg.exe"  # 여러분의 ffmpeg.exe 경로로 변경하세요

# 반복 재생 모드 설정
REPEAT_MODE = {
    "NONE": 0,      # 반복 없음
    "SINGLE": 1,    # 현재 노래 반복
    "ALL": 2,       # 전체 대기열 반복
}

# 컨트롤 UI 버튼 클래스
class MusicControlButtons(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)  # 버튼이 무기한 활성화되도록 설정
        self.ctx = ctx
        self.cog = ctx.cog
        
    @discord.ui.button(label="⏯️ 재생/정지", style=discord.ButtonStyle.primary)
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 연결되어 있는지 확인
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다!", ephemeral=True)
            
        # 재생 중인지 확인하고 토글
        try:
            if interaction.guild.voice_client.is_playing():
                # 일시 정지
                interaction.guild.voice_client.pause()
                await interaction.response.send_message("⏸️ 재생을 일시 정지했습니다.", ephemeral=True)
                
                # 컨트롤러 업데이트
                await self.cog.update_controller(interaction.guild)
            else:
                # 일시 정지 상태인지 확인
                if interaction.guild.voice_client.is_paused():
                    # 재생 재개
                    interaction.guild.voice_client.resume()
                    await interaction.response.send_message("▶️ 재생을 재개합니다.", ephemeral=True)
                    
                    # 컨트롤러 업데이트
                    await self.cog.update_controller(interaction.guild)
                else:
                    await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)
    
    @discord.ui.button(label="⏭️ 스킵", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 재생 중인지 확인
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
        
        # 서버 큐 가져오기
        server_queue = self.cog.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 플레이어를 찾을 수 없습니다!", ephemeral=True)
        
        # 로그 추가 (디버깅용)
        print(f"스킵 전 큐 상태: 현재 노래={server_queue.current.title if server_queue.current else 'None'}, 대기열 크기={server_queue.queue.qsize()}")
            
        # 스킵 처리
        interaction.guild.voice_client.stop()
        
        # 중요: 수동으로 next 이벤트 설정
        server_queue.next.set()
        
        # 이벤트 상태 로그
        print(f"스킵 후 next 이벤트 상태: {server_queue.next.is_set()}")
        
        await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다!")
        
    @discord.ui.button(label="⏹️ 중지", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 연결되어 있는지 확인
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다!", ephemeral=True)
            
        # 중지 처리
        server_queue = self.cog.players.get(interaction.guild.id)
        if server_queue:
            server_queue.queue = asyncio.Queue()  # 대기열 초기화
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
    @discord.ui.button(label="🔄 반복", style=discord.ButtonStyle.success)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 재생 중인지 확인
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
            
        # 반복 모드 변경
        server_queue = self.cog.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
            
        # 반복 모드 순환 (없음 -> 한 곡 -> 전체 -> 없음)
        if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
            server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
            await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
        elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
            server_queue.repeat_mode = REPEAT_MODE["ALL"]
            await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
        else:
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
        
        # 컨트롤러 업데이트
        await self.cog.update_controller(interaction.guild)
            
    @discord.ui.button(label="📋 대기열", style=discord.ButtonStyle.secondary)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 대기열 표시
        server_queue = self.cog.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 대기열이 비어있습니다!", ephemeral=True)
            
        # 대기열 임베드 생성
        await self.show_queue(interaction, server_queue)
    
    async def show_queue(self, interaction, server_queue):
        """대기열 표시 기능"""
        if not server_queue or (not server_queue.current and server_queue.queue.empty()):
            return await interaction.response.send_message("❌ 대기열이 비어있습니다!", ephemeral=True)
        
        # 큐에 있는 노래들을 리스트로 변환
        songs = []
        if server_queue.current:
            songs.append(server_queue.current)
            
        # 큐의 복사본 생성 (비동기 대기열은 직접 접근 어려움)
        temp_queue = asyncio.Queue()
        while not server_queue.queue.empty():
            song = await server_queue.queue.get()
            songs.append(song)
            await temp_queue.put(song)
            
        # 원래 큐 복원
        server_queue.queue = temp_queue
        
        # 임베드 생성
        embed = discord.Embed(
            title="🎵 재생 대기열",
            color=discord.Color.blue()
        )
        
        if len(songs) > 0:
            # 현재 재생 중인 노래
            current = songs[0]
            current_duration = f"{current.duration//60}:{current.duration%60:02d}" if current.duration else "알 수 없음"
            embed.add_field(
                name="지금 재생 중",
                value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']}) | `{current_duration}`",
                inline=False
            )
            
            # 대기 중인 노래들
            if len(songs) > 1:
                queue_text = ""
                for i, song in enumerate(songs[1:], 1):
                    if i > 10:  # 최대 10개까지만 표시
                        queue_text += f"... 그 외 {len(songs) - 11}곡"
                        break
                    
                    duration = f"{song.duration//60}:{song.duration%60:02d}" if song.duration else "알 수 없음"
                    queue_text += f"`{i}.` [{song.title}](https://www.youtube.com/watch?v={song.data['id']}) | `{duration}`\n"
                
                embed.add_field(
                    name="대기 중인 노래",
                    value=queue_text or "대기 중인 노래가 없습니다",
                    inline=False
                )
                
            # 총 재생 시간 계산
            total_duration = sum(song.duration for song in songs if song.duration)
            hours, remainder = divmod(total_duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                duration_str = f"{hours}시간 {minutes}분 {seconds}초"
            else:
                duration_str = f"{minutes}분 {seconds}초"
                
            embed.add_field(
                name="정보",
                value=f"▸ 총 곡 수: {len(songs)}곡\n▸ 총 재생 시간: {duration_str}",
                inline=False
            )
            
            # 반복 모드 상태
            repeat_mode = "없음"
            if server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                repeat_mode = "한 곡 반복 🔂"
            elif server_queue.repeat_mode == REPEAT_MODE["ALL"]:
                repeat_mode = "전체 반복 🔁"
                
            embed.add_field(
                name="반복 모드",
                value=repeat_mode,
                inline=True
            )
            
        else:
            embed.description = "대기열이 비어있습니다."
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

# 유튜브 검색 및 재생을 위한 클래스
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
            
            if 'entries' in data:
                # 플레이리스트에서 첫 번째 항목 가져오기
                data = data['entries'][0]
                
            if stream:
                # 스트리밍 모드에서는 URL 직접 사용
                filename = data['url']
            else:
                # 다운로드 모드에서는 파일명 사용
                filename = ytdl.prepare_filename(data)
            
            # FFmpeg 오류 처리 개선
            try:
                source = discord.FFmpegPCMAudio(
                    filename, 
                    executable=FFMPEG_PATH,
                    **ffmpeg_options
                )
                return cls(source, data=data)
            except Exception as e:
                print(f"FFmpeg 오디오 처리 중 오류: {e}")
                raise
                
        except Exception as e:
            print(f"음악 로드 중 오류: {e}")
            raise Exception(f"이 영상을 로드할 수 없습니다: {e}")

# 음악 큐 관리를 위한 클래스
class MusicPlayer:
    def __init__(self, ctx, cog=None):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = cog or ctx.cog  # cog 매개변수 직접 받기
        
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        
        self.current = None
        self.volume = 0.5
        self.repeat_mode = REPEAT_MODE["NONE"]  # 추가: 반복 모드 설정
        
        ctx.bot.loop.create_task(self.player_loop())
        
    async def player_loop(self):
        """음악 재생 루프"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next.clear()
            
            # 큐에서 다음 항목 가져오기
            try:
                async with asyncio.timeout(300):  # 5분 동안 대기
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                # 시간 초과시 음성 연결 종료
                await self.destroy(self.guild)
                return
            except Exception as e:
                print(f"대기열에서 곡을 가져오는 중 오류: {e}")
                continue  # 오류 발생 시 다음 반복으로
                
            # 음성 클라이언트가 연결되었는지 확인
            if not self.guild.voice_client:
                return
                
            # 현재 재생 중인 곡 설정
            self.current = source
            
            try:
                # after 콜백 함수 정의
                def after_playing(error):
                    if error:
                        print(f"재생 후 오류 발생: {error}")
                        # 오류 세부 정보 출력
                        import traceback
                        traceback.print_exc()
                    # 명시적으로 next 이벤트 설정
                    self.bot.loop.call_soon_threadsafe(self.next.set)
                
                # 노래 재생
                self.guild.voice_client.play(source, after=after_playing)
                
                # 버튼 UI가 있는 재생 중 메시지 표시
                embed = discord.Embed(
                    title="🎵 지금 재생 중",
                    description=f"[{source.title}](https://www.youtube.com/watch?v={source.data['id']})",
                    color=discord.Color.blue()
                )
                
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
                    
                if source.duration:
                    minutes, seconds = divmod(source.duration, 60)
                    embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}")
                
                # 안전하게 cog 확인 후 버튼 UI 생성
                if self.cog is not None:
                    try:
                        view = MusicControlButtons(self.cog._get_context_from_channel(self.channel))
                        
                        # 메시지 전송 시 오류 처리 추가
                        try:
                            await self.channel.send(embed=embed, view=view)
                        except Exception as e:
                            print(f"재생 메시지 전송 중 오류: {e}")
                        
                        # 컨트롤러 메시지 업데이트 (있는 경우)
                        try:
                            await self.cog.update_controller(self.guild)
                        except Exception as e:
                            print(f"컨트롤러 업데이트 중 오류: {e}")
                    except Exception as e:
                        print(f"버튼 UI 생성 중 오류: {e}")
                else:
                    print("경고: cog가 None입니다. 버튼 UI를 생성하지 않습니다.")
                    # 심플한 메시지만 전송
                    try:
                        await self.channel.send(embed=embed)
                    except Exception as e:
                        print(f"심플 메시지 전송 중 오류: {e}")
                
                # 다음 노래를 재생할 때까지 대기
                await self.next.wait()
                
            except Exception as e:
                print(f"노래 재생 중 오류: {e}")
                self.next.set()  # 오류 발생 시 다음 노래로 넘어가기
                continue
            
            # 반복 모드에 따른 처리
            try:
                if self.repeat_mode == REPEAT_MODE["SINGLE"]:
                    # 현재 노래 다시 큐에 추가
                    await self.queue.put(source)
                elif self.repeat_mode == REPEAT_MODE["ALL"] and self.current:
                    # 현재 노래를 큐 끝에 추가
                    await self.queue.put(source)
            except Exception as e:
                print(f"반복 모드 처리 중 오류: {e}")
            
            # 다음 노래를 위해 현재 소스 정리
            source.cleanup()
            self.current = None
            
            
    async def destroy(self, guild):
        """플레이어 정리 및 종료"""
        return self.bot.loop.create_task(self.cog.cleanup(guild))

# 음악 명령어 관리를 위한 Cog
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.controllers = {}  # 서버별 컨트롤러 메시지 저장
        self.music_channels = {}  # 서버별 음악 전용 채널 ID 저장
        self.load_music_channels()  # 저장된 음악 채널 정보 로드
        
    def load_music_channels(self):
        """저장된 음악 채널 정보를 로드합니다."""
        try:
            import json
            import os
            if os.path.exists('music_channels.json'):
                with open('music_channels.json', 'r') as f:
                    self.music_channels = json.load(f)
                    print(f"음악 채널 정보 로드 완료: {len(self.music_channels)}개")
        except Exception as e:
            print(f"음악 채널 정보 로드 중 오류: {e}")
            self.music_channels = {}

    def save_music_channels(self):
        """현재 음악 채널 정보를 파일에 저장합니다."""
        try:
            import json
            with open('music_channels.json', 'w') as f:
                json.dump(self.music_channels, f)
                print(f"음악 채널 정보 저장 완료: {len(self.music_channels)}개")
        except Exception as e:
            print(f"음악 채널 정보 저장 중 오류: {e}")
    
    async def load_music_channels_from_guild(self, guild):
        """서버 접속 시 해당 서버의 음악 채널 설정 복원"""
        guild_id = str(guild.id)
        if guild_id in self.music_channels:
            channel_id = self.music_channels[guild_id]
            try:
                channel = guild.get_channel(channel_id)
                if channel:
                    print(f"{guild.name}의 음악 채널 설정 복원: {channel.name}")
                    await self.create_controller_in_channel(channel)
            except Exception as e:
                print(f"음악 채널 복원 중 오류: {e}")
        
    async def cleanup(self, guild):
        """플레이어 정리 및 음성 연결 종료"""
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass
            
        try:
            del self.players[guild.id]
        except KeyError:
            pass
    
    def _get_context_from_channel(self, channel):
        """채널로부터 임시 컨텍스트 객체 생성"""
        # 버튼 인터랙션을 위한 임시 컨텍스트 생성
        fake_ctx = type('obj', (object,), {
            'bot': self.bot,
            'guild': channel.guild,
            'channel': channel,
            'cog': self,
            'voice_client': channel.guild.voice_client
        })
        return fake_ctx
    
    async def delete_messages_after(self, delay, *messages):
        """일정 시간 후 메시지를 삭제하는 헬퍼 메소드"""
        await asyncio.sleep(delay)
        for msg in messages:
            try:
                await msg.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # 메시지가 이미 삭제되었거나 권한이 없는 경우 무시
    
    async def delete_original_response_after(self, interaction, delay):
        """일정 시간 후 슬래시 명령어 응답을 삭제하는 메소드"""
        await asyncio.sleep(delay)
        try:
            await interaction.delete_original_response()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass  # 이미 삭제되었거나 권한이 없는 경우 무시
    
    async def create_controller_in_channel(self, channel):
        """지정된 채널에 컨트롤러를 생성하고 고정합니다."""
        # 이미 컨트롤러가 존재하는 경우 삭제
        guild = channel.guild
        if guild.id in self.controllers and self.controllers[guild.id]:
            try:
                try:
                    await self.controllers[guild.id].unpin()
                except:
                    pass
                await self.controllers[guild.id].delete()
            except Exception as e:
                print(f"기존 컨트롤러 삭제 중 오류: {e}")
        
        # 새 컨트롤러 임베드 생성
        embed = discord.Embed(
            title="🎤 콩인 노래방에 오신 것을 환영합니다!",
            description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.\n이 채널에 노래 제목만 입력해도 자동으로 재생됩니다!",
            color=discord.Color.blue()
        )
        
        # 현재 재생 중인 노래 정보 추가
        server_queue = self.players.get(guild.id)
        if server_queue and server_queue.current:
            current = server_queue.current
            embed.add_field(
                name="지금 재생 중",
                value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                inline=False
            )
            
            if current.thumbnail:
                embed.set_thumbnail(url=current.thumbnail)
                
            if current.duration:
                minutes, seconds = divmod(current.duration, 60)
                embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
                
            # 재생 상태
            play_status = "재생 중 ▶️"
            if guild.voice_client and guild.voice_client.is_paused():
                play_status = "일시 정지됨 ⏸️"
            embed.add_field(name="상태", value=play_status, inline=True)
        else:
            embed.add_field(
                name="지금 재생 중",
                value="재생 중인 노래가 없습니다.",
                inline=False
            )
        
        # 사용 안내 추가
        embed.set_footer(text="음악 전용 채널 | 채팅에 노래 제목만 입력하면 자동으로 재생됩니다")
        
        # 임시 컨텍스트 생성
        ctx = self._get_context_from_channel(channel)
        
        # 버튼 UI 생성
        view = MusicControlButtons(ctx)
        
        # 메시지 보내기
        message = await channel.send(embed=embed, view=view)
        self.controllers[guild.id] = message
        
        # 핀 설정
        try:
            await message.pin()
        except discord.HTTPException as e:
            print(f"컨트롤러 메시지 고정 실패: {e}")
            warning_msg = await channel.send("⚠️ 메시지를 고정할 수 없습니다. 봇에 메시지 고정 권한이 있는지 확인해주세요.")
            asyncio.create_task(self.delete_messages_after(10, warning_msg))
        
        return message
    
    async def update_controller(self, guild):
        """컨트롤러 메시지 업데이트"""
        if guild.id not in self.controllers:
            return
            
        controller_message = self.controllers[guild.id]
        if not controller_message:
            return
            
        try:
            # 임베드 생성
            embed = discord.Embed(
                title="🎮 음악 컨트롤러",
                description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
                color=discord.Color.blue()
            )
            
            # 현재 재생 중인 노래 정보 가져오기
            server_queue = self.players.get(guild.id)
            if not server_queue:
                embed.add_field(
                    name="지금 재생 중",
                    value="재생 중인 노래가 없습니다.",
                    inline=False
                )
            elif server_queue.current:
                current = server_queue.current
                embed.add_field(
                    name="지금 재생 중",
                    value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                    inline=False
                )
                
                if current.thumbnail:
                    embed.set_thumbnail(url=current.thumbnail)
                    
                if current.duration:
                    minutes, seconds = divmod(current.duration, 60)
                    embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
                    
                # 재생 상태
                play_status = "재생 중 ▶️"
                if guild.voice_client and guild.voice_client.is_paused():
                    play_status = "일시 정지됨 ⏸️"
                embed.add_field(name="상태", value=play_status, inline=True)
                    
                # 큐 정보
                queue_size = server_queue.queue.qsize()
                if queue_size > 0:
                    embed.add_field(name="대기열", value=f"{queue_size}곡", inline=True)
                    
                # 반복 모드 정보
                repeat_mode = "없음"
                if server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                    repeat_mode = "한 곡 반복 🔂"
                elif server_queue.repeat_mode == REPEAT_MODE["ALL"]:
                    repeat_mode = "전체 반복 🔁"
                    
                embed.add_field(name="반복 모드", value=repeat_mode, inline=True)
            else:
                embed.add_field(
                    name="지금 재생 중",
                    value="재생 중인 노래가 없습니다.",
                    inline=False
                )
                
            # 음악 채널인 경우 표시
            guild_id_str = str(guild.id)
            if guild_id_str in self.music_channels and self.music_channels[guild_id_str] == controller_message.channel.id:
                embed.set_footer(text="음악 전용 채널 | 채팅에 노래 제목만 입력하면 자동으로 재생됩니다")
            else:
                embed.set_footer(text="!도움말로 더 많은 명령어 확인하기")
                
            # 버튼 UI 생성
            view = MusicControlButtons(self._get_context_from_channel(controller_message.channel))
            
            # 메시지 업데이트 시도
            try:
                await controller_message.edit(embed=embed, view=view)
            except discord.HTTPException as e:
                print(f"컨트롤러 메시지 수정 실패: {e}")
                # 수정 실패 시 새 메시지 전송 시도
                try:
                    new_message = await controller_message.channel.send(embed=embed, view=view)
                    self.controllers[guild.id] = new_message
                    # 이전 메시지 삭제 시도
                    try:
                        await controller_message.delete()
                    except:
                        pass
                except Exception as e2:
                    print(f"새 컨트롤러 메시지 생성 실패: {e2}")
        except Exception as e:
            print(f"컨트롤러 업데이트 중 오류: {e}")
            
    def get_player(self, ctx):
        """서버에 플레이어 가져오기 또는 생성"""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx, self)  # self를 cog로 직접 전달
            self.players[ctx.guild.id] = player
            
        return player
    
    @commands.command(name='음악채널', aliases=['musicchannel', 'mc'])
    @commands.has_permissions(manage_channels=True)
    async def set_music_channel(self, ctx, action: str = "설정"):
        """현재 채널을 음악 전용 채널로 설정하거나 해제합니다."""
        guild_id = str(ctx.guild.id)  # JSON에서 키로 사용하기 위해 문자열로 변환
        
        if action.lower() in ["설정", "set", "지정"]:
            # 현재 채널을 음악 채널로 설정
            self.music_channels[guild_id] = ctx.channel.id
            self.save_music_channels()
            
            # 안내 임베드 생성
            embed = discord.Embed(
                title="🎵 음악 채널 설정 완료",
                description=f"**{ctx.channel.name}** 채널이 음악 전용 채널로 지정되었습니다.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="사용 방법",
                value="이 채널에 메시지를 입력하면 자동으로 노래를 검색하고 재생합니다.",
                inline=False
            )
            embed.add_field(
                name="컨트롤러",
                value="음악 컨트롤러가 채널 상단에 고정됩니다.",
                inline=False
            )
            embed.add_field(
                name="해제 방법",
                value="`!음악채널 해제` 명령어로 음악 채널 지정을 해제할 수 있습니다.",
                inline=False
            )
            
            response_msg = await ctx.send(embed=embed)
            
            # 컨트롤러 생성 및 고정
            await self.create_controller_in_channel(ctx.channel)
            
            # 명령어 메시지 삭제
            asyncio.create_task(self.delete_messages_after(5, ctx.message, response_msg))
            
        elif action.lower() in ["해제", "unset", "취소", "remove"]:
            # 음악 채널 설정 해제
            if guild_id in self.music_channels:
                del self.music_channels[guild_id]
                self.save_music_channels()
                
                embed = discord.Embed(
                    title="🎵 음악 채널 해제 완료",
                    description=f"**{ctx.channel.name}** 채널이 더 이상 음악 전용 채널이 아닙니다.",
                    color=discord.Color.blue()
                )
                response_msg = await ctx.send(embed=embed)
                
                # 명령어 메시지 삭제
                asyncio.create_task(self.delete_messages_after(5, ctx.message, response_msg))
            else:
                response_msg = await ctx.send("❌ 이 서버에는 지정된 음악 채널이 없습니다.")
                asyncio.create_task(self.delete_messages_after(5, ctx.message, response_msg))
        else:
            response_msg = await ctx.send("❌ 알 수 없는 명령어입니다. `!음악채널 설정` 또는 `!음악채널 해제`를 사용하세요.")
            asyncio.create_task(self.delete_messages_after(5, ctx.message, response_msg))
        
    @commands.command(name='재생', aliases=['play', 'p'])
    async def play(self, ctx, *, search: str):
        """노래를 검색하여 재생합니다."""
        # 음성 채널 확인
        if not ctx.author.voice:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        channel = ctx.author.voice.channel
        
        # 봇이 이미 음성 채널에 있는지 확인
        if ctx.voice_client is None:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)
            
        # 검색 메시지 표시
        loading_msg = await ctx.send(f"🔍 `{search}` 검색 중...")
        
        async with ctx.typing():
            try:
                # YouTube 검색 및 소스 생성
                source = await YTDLSource.from_url(f"ytsearch:{search}", loop=self.bot.loop, stream=True)
                
                # 플레이어 가져오기
                player = self.get_player(ctx)
                
                # 큐에 추가
                await player.queue.put(source)
                
                # 로딩 메시지 업데이트
                await loading_msg.edit(content=f"✅ **{source.title}**이(가) 대기열에 추가되었습니다!")
                
                # 컨트롤러 업데이트
                await self.update_controller(ctx.guild)
                
                # 일정 시간 후 메시지 삭제 (별도 태스크로 실행)
                asyncio.create_task(self.delete_messages_after(5, ctx.message, loading_msg))
                
            except Exception as e:
                await loading_msg.edit(content=f"❌ 오류 발생: {str(e)}")
                print(f"재생 중 오류: {e}")
                # 오류 메시지도 일정 시간 후 삭제
                asyncio.create_task(self.delete_messages_after(10, ctx.message, loading_msg))
                
    @commands.command(name='스킵', aliases=['skip', 's'])
    async def skip(self, ctx):
        """현재 재생 중인 노래를 건너뜁니다."""
        if not ctx.voice_client:
            return await ctx.send("❌ 재생 중인 노래가 없습니다!")
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        if ctx.voice_client.is_playing():
            # 서버 큐 가져오기
            server_queue = self.players.get(ctx.guild.id)
            if server_queue:
                # 로그 추가
                print(f"스킵 명령어 실행: 현재 노래={server_queue.current.title if server_queue.current else 'None'}")
                
                # 스킵 처리
                ctx.voice_client.stop()
                
                # 수동으로 next 이벤트 설정
                server_queue.next.set()
                
                print(f"스킵 후 next 이벤트 상태: {server_queue.next.is_set()}")
                
            skip_msg = await ctx.send("⏭️ 노래를 건너뛰었습니다!")
            # 메시지 자동 삭제
            asyncio.create_task(self.delete_messages_after(5, ctx.message, skip_msg))
            
    @commands.command(name='중지', aliases=['stop'])
    async def stop(self, ctx):
        """재생을 중지하고 음성 채널에서 나갑니다."""
        if not ctx.voice_client:
            return await ctx.send("❌ 음성 채널에 연결되어 있지 않습니다!")
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        await self.cleanup(ctx.guild)
        stop_msg = await ctx.send("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
        # 메시지 자동 삭제
        asyncio.create_task(self.delete_messages_after(5, ctx.message, stop_msg))
        
        # 컨트롤러 업데이트
        await self.update_controller(ctx.guild)
    
    @commands.command(name='대기열', aliases=['queue', 'q'])
    async def queue(self, ctx):
        """현재 재생 대기열을 표시합니다."""
        server_queue = self.players.get(ctx.guild.id)
        if not server_queue:
            queue_msg = await ctx.send("❌ 대기열이 비어있습니다!")
            # 메시지 자동 삭제
            asyncio.create_task(self.delete_messages_after(5, ctx.message, queue_msg))
            return
            
        # 임시 컨텍스트 생성
        fake_ctx = self._get_context_from_channel(ctx.channel)
        
        # 대기열 표시
        buttons = MusicControlButtons(fake_ctx)
        await buttons.show_queue(ctx, server_queue)
        
        # 명령어 메시지 삭제
        asyncio.create_task(self.delete_messages_after(3, ctx.message))
    
    @commands.command(name='반복', aliases=['repeat', 'loop'])
    async def repeat(self, ctx, mode: str = None):
        """반복 모드를 설정합니다."""
        if not ctx.voice_client:
            repeat_err = await ctx.send("❌ 재생 중인 노래가 없습니다!")
            asyncio.create_task(self.delete_messages_after(5, ctx.message, repeat_err))
            return
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            repeat_err = await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            asyncio.create_task(self.delete_messages_after(5, ctx.message, repeat_err))
            return
            
        server_queue = self.players.get(ctx.guild.id)
        if not server_queue:
            repeat_err = await ctx.send("❌ 재생 중인 노래가 없습니다!")
            asyncio.create_task(self.delete_messages_after(5, ctx.message, repeat_err))
            return
        
        repeat_msg = None
        if mode is None:
            # 모드를 지정하지 않으면 순환
            if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                repeat_msg = await ctx.send("🔂 현재 노래를 반복합니다.")
            elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                repeat_msg = await ctx.send("🔁 전체 대기열을 반복합니다.")
            else:
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                repeat_msg = await ctx.send("▶️ 반복 모드를 해제했습니다.")
        elif mode.lower() in ['off', '해제', '없음']:
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            repeat_msg = await ctx.send("▶️ 반복 모드를 해제했습니다.")
        elif mode.lower() in ['single', '한곡', '노래']:
            server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
            repeat_msg = await ctx.send("🔂 현재 노래를 반복합니다.")
        elif mode.lower() in ['all', '전체', '큐']:
            server_queue.repeat_mode = REPEAT_MODE["ALL"]
            repeat_msg = await ctx.send("🔁 전체 대기열을 반복합니다.")
        else:
            repeat_msg = await ctx.send("❌ 알 수 없는 모드입니다. `!반복`, `!반복 한곡`, `!반복 전체`, `!반복 해제` 중 하나를 사용하세요.")
            
        # 메시지 자동 삭제
        if repeat_msg:
            asyncio.create_task(self.delete_messages_after(5, ctx.message, repeat_msg))
            
        # 컨트롤러 업데이트
        await self.update_controller(ctx.guild)
        
    @commands.command(name='컨트롤러', aliases=['controller', 'c'])
    async def controller(self, ctx):
        """음악 컨트롤러를 채팅방 상단에 고정합니다."""
        # 임시 응답 메시지 전송
        temp_msg = await ctx.send("🎮 컨트롤러 생성 중...")
        
        try:
            # 이미 컨트롤러가 존재하는 경우 삭제
            if ctx.guild.id in self.controllers and self.controllers[ctx.guild.id]:
                try:
                    # 고정된 메시지라면 고정 해제
                    try:
                        await self.controllers[ctx.guild.id].unpin()
                    except:
                        pass
                    # 메시지 삭제
                    await self.controllers[ctx.guild.id].delete()
                except Exception as e:
                    print(f"기존 컨트롤러 삭제 중 오류: {e}")
                    
            # 새 컨트롤러 메시지 생성
            embed = discord.Embed(
                title="🎮 음악 컨트롤러",
                description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
                color=discord.Color.blue()
            )
            
            # 현재 재생 중인 노래 정보 추가
            server_queue = self.players.get(ctx.guild.id)
            if server_queue and server_queue.current:
                current = server_queue.current
                embed.add_field(
                    name="지금 재생 중",
                    value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                    inline=False
                )
                
                if current.thumbnail:
                    embed.set_thumbnail(url=current.thumbnail)
                    
                if current.duration:
                    minutes, seconds = divmod(current.duration, 60)
                    embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
                    
                # 재생 상태
                play_status = "재생 중 ▶️"
                if ctx.guild.voice_client and ctx.guild.voice_client.is_paused():
                    play_status = "일시 정지됨 ⏸️"
                embed.add_field(name="상태", value=play_status, inline=True)
            else:
                embed.add_field(
                    name="지금 재생 중",
                    value="재생 중인 노래가 없습니다.",
                    inline=False
                )
            
            # 사용 안내 추가
            embed.set_footer(text="메시지를 고정하여 항상 접근할 수 있습니다 | '!도움말'로 더 많은 정보 확인")
            
            # 버튼 UI 생성
            view = MusicControlButtons(self._get_context_from_channel(ctx.channel))
            
            # 메시지 보내기
            message = await ctx.send(embed=embed, view=view)
            self.controllers[ctx.guild.id] = message
            
            # 임시 메시지 업데이트 및 자동 삭제
            await temp_msg.edit(content="✅ 컨트롤러가 생성되었습니다!")
            asyncio.create_task(self.delete_messages_after(3, temp_msg, ctx.message))
            
            # 핀 설정
            try:
                await message.pin()
            except discord.HTTPException as e:
                print(f"메시지 고정 실패: {e}")
                warning_msg = await ctx.send("⚠️ 메시지를 고정할 수 없습니다. 권한을 확인해주세요.")
                asyncio.create_task(self.delete_messages_after(10, warning_msg))
        except Exception as e:
            await temp_msg.edit(content=f"❌ 컨트롤러 생성 중 오류 발생: {str(e)}")
            print(f"컨트롤러 생성 오류: {e}")
            # 오류 메시지 자동 삭제
            asyncio.create_task(self.delete_messages_after(10, temp_msg, ctx.message))
    
    @commands.command(name='도움말', aliases=['h', 'help'])
    async def help(self, ctx):
        """명령어 도움말을 표시합니다."""
        embed = discord.Embed(
            title="🎵 음악 봇 도움말",
            description="채팅에 노래 제목만 입력해도 자동으로 재생됩니다!",
            color=discord.Color.blue()
        )
        
        # 명령어 목록
        commands_section = (
            "**!재생 [노래 제목]** - 노래를 검색하여 재생합니다\n"
            "**!스킵** - 현재 재생 중인 노래를 건너뜁니다\n"
            "**!중지** - 재생을 중지하고 음성 채널에서 나갑니다\n"
            "**!대기열** - 현재 재생 대기열을 표시합니다\n"
            "**!반복 [한곡/전체/해제]** - 반복 모드를 설정합니다\n"
            "**!컨트롤러** - 음악 컨트롤러를 채팅방 상단에 고정합니다\n"
            "**!음악채널 [설정/해제]** - 현재 채널을 음악 전용 채널로 설정합니다"
        )
        embed.add_field(name="💬 채팅 명령어", value=commands_section, inline=False)
        
        # 컨트롤러 버튼 설명
        controls_section = (
            "**⏯️ 재생/정지** - 음악을 재생하거나 일시 정지합니다\n"
            "**⏭️ 스킵** - 현재 노래를 건너뜁니다\n"
            "**⏹️ 중지** - 재생을 중지하고 음성 채널에서 나갑니다\n"
            "**🔄 반복** - 반복 모드를 변경합니다\n"
            "**📋 대기열** - 현재 대기열을 표시합니다"
        )
        embed.add_field(name="🎮 컨트롤러 버튼", value=controls_section, inline=False)
        
        # 음악 채널 설명 추가
        music_channel_section = (
            "음악 전용 채널을 설정하면, 해당 채널에서는 일반 메시지가 자동으로 음악 재생 요청으로 처리됩니다.\n"
            "또한 음악 컨트롤러가 채널 상단에 고정되어 편리하게 음악을 제어할 수 있습니다."
        )
        embed.add_field(name="🎧 음악 전용 채널", value=music_channel_section, inline=False)
        
        # 슬래시 명령어 정보
        embed.add_field(
            name="/ 슬래시 명령어",
            value="모든 기능은 `/명령어`로도 사용할 수 있습니다!",
            inline=False
        )
        
        # 팁 추가
        embed.add_field(
            name="💡 팁",
            value="음성 채널에 있는 상태에서 노래 제목만 채팅에 입력해도 자동으로 재생됩니다!",
            inline=False
        )
        
        # 푸터 추가
        embed.set_footer(text="음악 봇 도움말 | 봇이 보내는 메시지는 5초 후 자동으로 삭제됩니다")
        
        help_msg = await ctx.send(embed=embed)
        # 도움말 명령어는 삭제하지 않고 메시지만 삭제
        asyncio.create_task(self.delete_messages_after(3, ctx.message))

    # 슬래시 명령어 (앱 명령어) 구현
    @app_commands.command(name="재생", description="노래를 검색하여 재생합니다")
    async def slash_play(self, interaction: discord.Interaction, *, 검색어: str):
        # 음성 채널 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        channel = interaction.user.voice.channel
        
        # 봇이 이미 음성 채널에 있는지 확인
        if interaction.guild.voice_client is None:
            await channel.connect()
        elif interaction.guild.voice_client.channel != channel:
            await interaction.guild.voice_client.move_to(channel)
        
        # 로딩 메시지 표시
        await interaction.response.send_message(f"🔍 `{검색어}` 검색 중...")
        
        try:
            # 임시 컨텍스트 생성
            ctx = self._get_context_from_interaction(interaction)
            
            # YouTube 검색 및 소스 생성
            source = await YTDLSource.from_url(f"ytsearch:{검색어}", loop=self.bot.loop, stream=True)
            
            # 플레이어 가져오기
            player = self.get_player(ctx)
            
            # 큐에 추가
            await player.queue.put(source)
            
            # 메시지 업데이트
            await interaction.edit_original_response(content=f"✅ **{source.title}**이(가) 대기열에 추가되었습니다!")
            
            # 컨트롤러 업데이트
            await self.update_controller(interaction.guild)
            
            # 일정 시간 후 메시지 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ 오류 발생: {str(e)}")
            print(f"재생 중 오류: {e}")
            # 오류 메시지도 일정 시간 후 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 10))
    
    @app_commands.command(name="스킵", description="현재 재생 중인 노래를 건너뜁니다")
    async def slash_skip(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        if interaction.guild.voice_client.is_playing():
            # 서버 큐 가져오기
            server_queue = self.players.get(interaction.guild.id)
            if server_queue:
                # 로그 추가
                print(f"슬래시 스킵 명령어 실행: 현재 노래={server_queue.current.title if server_queue.current else 'None'}")
                
                # 스킵 처리
                interaction.guild.voice_client.stop()
                
                # 수동으로 next 이벤트 설정
                server_queue.next.set()
                
                print(f"스킵 후 next 이벤트 상태: {server_queue.next.is_set()}")
                
            await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다!")
            # 메시지 자동 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
        else:
            await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
    
    @app_commands.command(name="중지", description="재생을 중지하고 음성 채널에서 나갑니다")
    async def slash_stop(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다!")
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        await self.cleanup(interaction.guild)
        await interaction.response.send_message("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
        # 메시지 자동 삭제
        asyncio.create_task(self.delete_original_response_after(interaction, 5))
        
        # 컨트롤러 업데이트
        await self.update_controller(interaction.guild)
    
    @app_commands.command(name="대기열", description="현재 재생 대기열을 표시합니다")
    async def slash_queue(self, interaction: discord.Interaction):
        server_queue = self.players.get(interaction.guild.id)
        if not server_queue:
            await interaction.response.send_message("❌ 대기열이 비어있습니다!")
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            return
            
        # 임시 컨텍스트 생성
        ctx = self._get_context_from_interaction(interaction)
        
        # 대기열 표시
        buttons = MusicControlButtons(ctx)
        await interaction.response.defer()
        await buttons.show_queue(interaction, server_queue)
    
    @app_commands.command(name="반복", description="반복 모드를 설정합니다")
    @app_commands.choices(모드=[
        app_commands.Choice(name="한곡 반복", value="한곡"),
        app_commands.Choice(name="전체 반복", value="전체"),
        app_commands.Choice(name="반복 해제", value="해제")
    ])
    async def slash_repeat(self, interaction: discord.Interaction, 모드: app_commands.Choice[str] = None):
        if not interaction.guild.voice_client:
            await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            return
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            return
            
        server_queue = self.players.get(interaction.guild.id)
        if not server_queue:
            await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            return
            
        if 모드 is None:
            # 모드를 지정하지 않으면 순환
            if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
            elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
            else:
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
        else:
            # 선택한 모드로 설정
            if 모드.value == "한곡":
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
            elif 모드.value == "전체":
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
            else:  # "해제"
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
        
        # 메시지 자동 삭제
        asyncio.create_task(self.delete_original_response_after(interaction, 5))
                
        # 컨트롤러 업데이트
        await self.update_controller(interaction.guild)

    @app_commands.command(name="음악채널", description="현재 채널을 음악 전용 채널로 설정하거나 해제합니다")
    @app_commands.describe(action="설정 또는 해제")
    @app_commands.choices(action=[
        app_commands.Choice(name="설정", value="설정"),
        app_commands.Choice(name="해제", value="해제")
    ])
    @app_commands.default_permissions(manage_channels=True)
    async def slash_set_music_channel(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        """현재 채널을 음악 전용 채널로 설정하거나 해제합니다."""
        guild_id = str(interaction.guild.id)
        channel = interaction.channel
        
        if action.value == "설정":
            # 현재 채널을 음악 채널로 설정
            self.music_channels[guild_id] = channel.id
            self.save_music_channels()
            
            # 안내 임베드 생성
            embed = discord.Embed(
                title="🎵 음악 채널 설정 완료",
                description=f"**{channel.name}** 채널이 음악 전용 채널로 지정되었습니다.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="사용 방법",
                value="이 채널에 메시지를 입력하면 자동으로 노래를 검색하고 재생합니다.",
                inline=False
            )
            embed.add_field(
                name="컨트롤러",
                value="음악 컨트롤러가 채널 상단에 고정됩니다.",
                inline=False
            )
            embed.add_field(
                name="해제 방법",
                value="`/음악채널 해제` 명령어로 음악 채널 지정을 해제할 수 있습니다.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
            # 컨트롤러 생성 및 고정
            await self.create_controller_in_channel(channel)
            
            # 응답 메시지 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 5))
            
        elif action.value == "해제":
            # 음악 채널 설정 해제
            if guild_id in self.music_channels:
                del self.music_channels[guild_id]
                self.save_music_channels()
                
                embed = discord.Embed(
                    title="🎵 음악 채널 해제 완료",
                    description=f"**{channel.name}** 채널이 더 이상 음악 전용 채널이 아닙니다.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed)
                
                # 응답 메시지 삭제
                asyncio.create_task(self.delete_original_response_after(interaction, 5))
            else:
                await interaction.response.send_message("❌ 이 서버에는 지정된 음악 채널이 없습니다.")
                asyncio.create_task(self.delete_original_response_after(interaction, 5))
    
    @app_commands.command(name="컨트롤러", description="음악 컨트롤러를 채팅방 상단에 고정합니다")
    async def slash_controller(self, interaction: discord.Interaction):
        # 응답 전송
        await interaction.response.send_message("🎮 컨트롤러 생성 중...")
        
        try:
            # 이미 컨트롤러가 존재하는 경우 삭제
            if interaction.guild.id in self.controllers and self.controllers[interaction.guild.id]:
                try:
                    # 고정된 메시지라면 고정 해제
                    try:
                        await self.controllers[interaction.guild.id].unpin()
                    except:
                        pass
                    # 메시지 삭제
                    await self.controllers[interaction.guild.id].delete()
                except Exception as e:
                    print(f"기존 컨트롤러 삭제 중 오류: {e}")
                    
            # 새 컨트롤러 메시지 생성
            embed = discord.Embed(
                title="🎮 음악 컨트롤러",
                description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
                color=discord.Color.blue()
            )
            
            # 현재 재생 중인 노래 정보 추가
            server_queue = self.players.get(interaction.guild.id)
            if server_queue and server_queue.current:
                current = server_queue.current
                embed.add_field(
                    name="지금 재생 중",
                    value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                    inline=False
                )
                
                if current.thumbnail:
                    embed.set_thumbnail(url=current.thumbnail)
                    
                if current.duration:
                    minutes, seconds = divmod(current.duration, 60)
                    embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}", inline=True)
                    
                # 재생 상태
                play_status = "재생 중 ▶️"
                if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
                    play_status = "일시 정지됨 ⏸️"
                embed.add_field(name="상태", value=play_status, inline=True)
            else:
                embed.add_field(
                    name="지금 재생 중",
                    value="재생 중인 노래가 없습니다.",
                    inline=False
                )
            
            # 사용 안내 추가
            embed.set_footer(text="메시지를 고정하여 항상 접근할 수 있습니다 | '/도움말'로 더 많은 정보 확인")
            
            # 임시 컨텍스트 생성
            ctx = self._get_context_from_interaction(interaction)
            
            # 버튼 UI 생성
            view = MusicControlButtons(ctx)
            
            # 메시지 보내기
            message = await interaction.channel.send(embed=embed, view=view)
            self.controllers[interaction.guild.id] = message
            
            # 원래 메시지 수정
            await interaction.edit_original_response(content="✅ 컨트롤러가 생성되었습니다!")
            
            # 슬래시 명령어 응답 자동 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 3))
            
            # 핀 설정
            try:
                await message.pin()
            except discord.HTTPException as e:
                print(f"메시지 고정 실패: {e}")
                await interaction.followup.send("⚠️ 메시지를 고정할 수 없습니다. 권한을 확인해주세요.", ephemeral=True)
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ 컨트롤러 생성 중 오류 발생: {str(e)}")
            print(f"컨트롤러 생성 오류: {e}")
            # 오류 메시지도 자동 삭제
            asyncio.create_task(self.delete_original_response_after(interaction, 10))
    
    def _get_context_from_interaction(self, interaction):
        """Interaction에서 임시 컨텍스트 객체 생성"""
        fake_ctx = type('obj', (object,), {
            'bot': self.bot,
            'guild': interaction.guild,
            'channel': interaction.channel,
            'cog': self,
            'voice_client': interaction.guild.voice_client
        })
        return fake_ctx

# 서버 재시작 시 음악 채널 설정 복원 함수
async def restore_music_channels():
    """모든 서버의 음악 채널 설정을 복원합니다."""
    music_cog = bot.get_cog('Music')
    if music_cog:
        for guild in bot.guilds:
            await music_cog.load_music_channels_from_guild(guild)

# Cog 등록 및 봇 실행
async def setup():
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    
    # 슬래시 명령어 동기화
    try:
        # 슬래시 명령어 등록
        await bot.tree.sync()
        print("슬래시 명령어가 성공적으로 동기화되었습니다.")
    except Exception as e:
        print(f"슬래시 명령어 동기화 중 오류 발생: {e}")
    
@bot.event
async def on_ready():
    # 시작 시간 기록 (업타임 계산용)
    bot.start_time = datetime.datetime.now()
    
    # 로그 출력 개선
    print(f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print(f'✅ {bot.user.name}이(가) 온라인 상태입니다!')
    print(f'🕒 시작 시간: {bot.start_time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'🤖 봇 ID: {bot.user.id}')
    print(f'📊 서버 수: {len(bot.guilds)}개')
    print(f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    
    # Cog 설정
    await setup()
    
    # 음악 채널 설정 복원
    await restore_music_channels()
    
    # 봇 상태 업데이트 함수 생성 (매 30분마다 메시지 변경)
    async def update_presence():
        statuses = [
            ("/재생 또는 !재생 | 음악 봇", discord.ActivityType.listening),
            ("음악과 함께하는 시간", discord.ActivityType.playing),
            ("이제 채팅에 노래 제목만 입력해도 재생됩니다!", discord.ActivityType.listening),
            (f"{len(bot.guilds)}개 서버에서 음악 재생 중", discord.ActivityType.playing),
            ("!도움말 | 도움말 확인하기", discord.ActivityType.watching)
        ]
        
        status_index = 0
        while not bot.is_closed():
            status_text, activity_type = statuses[status_index]
            await bot.change_presence(
                activity=discord.Activity(
                    type=activity_type,
                    name=status_text
                )
            )
            status_index = (status_index + 1) % len(statuses)
            await asyncio.sleep(1800)  # 30분마다 상태 메시지 변경
    
    # 상태 업데이트 태스크 시작
    bot.loop.create_task(update_presence())

# 새 서버에 참가했을 때 설정 복원
@bot.event 
async def on_guild_join(guild):
    """새 서버에 참가했을 때 호출"""
    music_cog = bot.get_cog('Music')
    if music_cog:
        await music_cog.load_music_channels_from_guild(guild)

# 에러 핸들링
@bot.event
async def on_command_error(ctx, error):
    try:
        # 명령어 없음 오류
        if isinstance(error, commands.CommandNotFound):
            # 명령어를 찾을 수 없는 경우, 유사한 명령어인지 확인
            search_term = ctx.message.content.lstrip('!').split()[0]
            
            # 명령어로 인식되지 않은 채팅이 노래 제목인지 확인 (접두사 없는 명령어)
            if not search_term.startswith('!') and len(search_term) > 1:
                # Music 코그 가져오기
                music_cog = bot.get_cog('Music')
                if music_cog:
                    # 비동기 처리로 변경
                    asyncio.create_task(music_cog.play(ctx, search=ctx.message.content))
                    return
                
            # 오류 메시지 전송 및 자동 삭제
            error_msg = await ctx.send("❌ 알 수 없는 명령어입니다. `!도움말`을 입력하여 명령어 목록을 확인하세요.")
            # Music 코그가 있으면 메시지 자동 삭제 기능 사용
            music_cog = bot.get_cog('Music')
            if music_cog:
                asyncio.create_task(music_cog.delete_messages_after(5, ctx.message, error_msg))
                
        # 필수 인자 누락 오류
        elif isinstance(error, commands.MissingRequiredArgument):
            if ctx.command.name in ["재생", "play", "p"]:
                error_msg = await ctx.send("❌ 노래 제목을 입력해주세요. 예시: `!재생 아이유 좋은날`")
            else:
                error_msg = await ctx.send(f"❌ 명령어 사용법이 잘못되었습니다. `!도움말`을 입력하여 명령어 사용법을 확인하세요.")
                
            # 오류 메시지 자동 삭제
            music_cog = bot.get_cog('Music')
            if music_cog:
                asyncio.create_task(music_cog.delete_messages_after(5, ctx.message, error_msg))
        
        # 권한 부족 오류
        elif isinstance(error, commands.MissingPermissions):
            error_msg = await ctx.send("❌ 이 명령어를 실행할 권한이 없습니다.")
            music_cog = bot.get_cog('Music')
            if music_cog:
                asyncio.create_task(music_cog.delete_messages_after(5, ctx.message, error_msg))
                
        # 권한 오류
        elif isinstance(error, commands.MissingPermissions) or isinstance(error, discord.Forbidden):
            error_msg = await ctx.send("❌ 이 명령어를 실행할 권한이 없습니다.")
            # 오류 메시지 자동 삭제
            music_cog = bot.get_cog('Music')
            if music_cog:
                asyncio.create_task(music_cog.delete_messages_after(5, ctx.message, error_msg))
                
        # 기타 오류
        else:
            print(f"명령어 오류 발생: {type(error).__name__}: {error}")
            error_msg = await ctx.send(f"❌ 명령어 실행 중 오류가 발생했습니다: {type(error).__name__}")
            # 오류 메시지 자동 삭제
            music_cog = bot.get_cog('Music')
            if music_cog:
                asyncio.create_task(music_cog.delete_messages_after(5, ctx.message, error_msg))
    except Exception as e:
        # 예외 처리 중 발생한 오류 로깅
        print(f"명령어 오류 처리 중 추가 오류 발생: {e}")

# 디버깅 에러 핸들링
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"이벤트 {event}에서 오류 발생:")
    import traceback
    traceback.print_exc()

# 일반 채팅 메시지 처리 (접두사 없이 노래 제목만 입력 시 재생)
@bot.event
async def on_message(message):
    try:
        # 봇 메시지 무시
        if message.author.bot:
            return
        
        # 음악 전용 채널 확인
        music_cog = bot.get_cog('Music')
        if music_cog and str(message.guild.id) in music_cog.music_channels:
            # 현재 채널이 음악 전용 채널인지 확인
            if message.channel.id == music_cog.music_channels[str(message.guild.id)]:
                # 명령어가 아닌 모든 메시지를 음악 재생 요청으로 처리
                if not message.content.startswith('!') and not message.content.startswith('/'):
                    # 컨텍스트 생성
                    ctx = await bot.get_context(message)
                    
                    # 음성 채널 확인
                    if message.author.voice and message.author.voice.channel:
                        # 재생 명령어 실행
                        asyncio.create_task(music_cog.play(ctx, search=message.content))
                        return
                    else:
                        # 음성 채널에 없는 경우 안내 메시지
                        error_msg = await message.channel.send("❌ 음성 채널에 먼저 입장해주세요!")
                        asyncio.create_task(music_cog.delete_messages_after(5, message, error_msg))
                        return
        
        # 슬래시 명령어나 일반 명령어는 처리 후 바로 리턴
        if message.content.startswith('!') or message.content.startswith('/'):
            await bot.process_commands(message)
            return
        
        # 짧은 메시지 (1-2단어) 또는 짧은 단일 단어는 명령어로 처리
        words = message.content.split()
        if len(words) < 2 and len(message.content) < 10:
            await bot.process_commands(message)
            return
        
        # 음성 채널에 있는 사용자만 메시지로 노래 요청 가능
        if message.author.voice and message.author.voice.channel:
            # 재생 명령어와 같은 기능으로 처리
            ctx = await bot.get_context(message)
            music_cog = bot.get_cog('Music')
            if music_cog:
                # 비동기 처리로 변경하여 봇의 응답성 유지
                asyncio.create_task(music_cog.play(ctx, search=message.content))
                return
        
        # 일반 메시지로 처리
        await bot.process_commands(message)
    except Exception as e:
        print(f"메시지 처리 중 오류 발생: {e}")
        # 오류가 발생해도 기본 명령어 처리는 시도
        try:
            await bot.process_commands(message)
        except:
            pass

# 봇 실행
bot.run(TOKEN)
